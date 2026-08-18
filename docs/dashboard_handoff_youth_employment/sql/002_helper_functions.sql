-- =============================================================================
-- 002_helper_functions.sql
--
-- The small-numbers policy, confidence intervals, and funnel-plot verdicts.
--
-- THE RULE THIS FILE EXISTS TO ENFORCE:
-- no rate is ever displayed without passing through rpt.rate_label() or
-- rpt.safe_rate(). Suppression is enforced here, once, not re-implemented in
-- each Metabase question. A question that computes `count(*) filter (...) * 100.0
-- / count(*)` inline is a bug, and code review should reject it.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- rpt.suppression_band(denominator)
-- -----------------------------------------------------------------------------
-- 'report'      denominator >= 30   show the rate normally
-- 'provisional' 10 <= denominator < 30   show with a marker, never rank or compare
-- 'suppress'    denominator < 10    show 'too few to assess', numerator withheld
--
-- Thresholds follow NCHS Data Presentation Standards for Proportions (effective
-- sample size >= 30) and state small-numbers policies. They are parameters, not
-- constants: the World Bank task team may prescribe its own (README OQ-8).

CREATE OR REPLACE FUNCTION rpt.suppression_band(p_denominator integer)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT CASE
        WHEN p_denominator IS NULL                                     THEN 'suppress'
        WHEN p_denominator <  (SELECT suppress_below_n    FROM rpt.reporting_parameters WHERE id = 1) THEN 'suppress'
        WHEN p_denominator <  (SELECT provisional_below_n FROM rpt.reporting_parameters WHERE id = 1) THEN 'provisional'
        ELSE 'report'
    END;
$$;

-- -----------------------------------------------------------------------------
-- rpt.safe_rate(numerator, denominator)
-- -----------------------------------------------------------------------------
-- Returns the rate as a percentage rounded to whole points, or NULL when the
-- denominator falls in the suppress band. NULL is deliberate: a NULL renders as
-- a blank or an em dash in Metabase and cannot be accidentally charted, whereas
-- a 0 would be plotted as a real value.

CREATE OR REPLACE FUNCTION rpt.safe_rate(p_numerator integer, p_denominator integer)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT CASE
        WHEN rpt.suppression_band(p_denominator) = 'suppress' THEN NULL
        WHEN p_denominator = 0 THEN NULL
        ELSE round(100.0 * p_numerator / p_denominator)
    END;
$$;

-- -----------------------------------------------------------------------------
-- rpt.rate_label(numerator, denominator)
-- -----------------------------------------------------------------------------
-- The display string. Always carries the denominator, because a percentage
-- without its denominator is the single most common way these dashboards mislead.
--   '64% (115/180)'
--   '52%* (14/27)'   provisional
--   'too few to assess (n=8)'   suppressed: the NUMERATOR IS NOT SHOWN
--
-- The suppressed branch deliberately withholds the numerator. Publishing
-- '- (5/8)' suppresses the percentage while handing over the exact counts it
-- was computed from, which defeats the purpose. The denominator is retained
-- because it is what tells the reader why the cell is suppressed.

CREATE OR REPLACE FUNCTION rpt.rate_label(p_numerator integer, p_denominator integer)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT CASE rpt.suppression_band(p_denominator)
        WHEN 'suppress'    THEN format('too few to assess (n=%s)', p_denominator)
        WHEN 'provisional' THEN format('%s%%* (%s/%s)',
                                       rpt.safe_rate(p_numerator, p_denominator),
                                       p_numerator, p_denominator)
        ELSE                    format('%s%% (%s/%s)',
                                       rpt.safe_rate(p_numerator, p_denominator),
                                       p_numerator, p_denominator)
    END;
$$;

-- Where disclosure rules forbid showing even the denominator of a suppressed
-- cell, use this variant instead.
CREATE OR REPLACE FUNCTION rpt.rate_label_nocounts(p_numerator integer, p_denominator integer)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT CASE rpt.suppression_band(p_denominator)
        WHEN 'suppress'    THEN 'too few to report'
        WHEN 'provisional' THEN format('%s%%* (n=%s)', rpt.safe_rate(p_numerator, p_denominator), p_denominator)
        ELSE                    format('%s%% (n=%s)',  rpt.safe_rate(p_numerator, p_denominator), p_denominator)
    END;
$$;

-- -----------------------------------------------------------------------------
-- Wilson score interval
-- -----------------------------------------------------------------------------
-- Used instead of the normal approximation because it behaves correctly at
-- proportions near 0 and 1 and at small n, which is most of this dataset.
-- z = 1.96 for a 95% interval.

CREATE OR REPLACE FUNCTION rpt.wilson_bounds(
    p_numerator   integer,
    p_denominator integer,
    p_z           numeric DEFAULT 1.96
)
RETURNS TABLE (lower_pct numeric, upper_pct numeric)
LANGUAGE sql
STABLE
AS $$
    WITH s AS (
        SELECT
            p_denominator::numeric                                        AS n,
            CASE WHEN p_denominator > 0
                 THEN p_numerator::numeric / p_denominator
                 ELSE NULL END                                            AS p,
            p_z::numeric                                                  AS z
    ),
    calc AS (
        SELECT
            (p + z * z / (2 * n)) / (1 + z * z / n)                       AS centre,
            (z * sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n) AS margin
        FROM s
        WHERE n > 0 AND p IS NOT NULL
    )
    SELECT
        round(100 * greatest(centre - margin, 0)),
        round(100 * least(centre + margin, 1))
    FROM calc;
$$;

COMMENT ON FUNCTION rpt.wilson_bounds(integer, integer, numeric) IS
  'Wilson score interval, returned as whole percentage points. Preferred over the normal '
  'approximation at small n and at proportions near 0 or 1.';

-- -----------------------------------------------------------------------------
-- rpt.funnel_verdict(numerator, denominator, overall_rate)
-- -----------------------------------------------------------------------------
-- Spiegelhalter funnel-plot logic, reduced to a three-state flag so a programme
-- manager does not have to learn to read a funnel plot.
--
-- Control limits are computed at the funnel_z parameter (3.09 ≈ 99.8%) around
-- the OVERALL PROGRAMME RATE, not around a target. Limits widen as the
-- denominator shrinks, which is exactly why a partner with 27 referrals cannot
-- be flagged as an outlier and a partner with 180 can.
--
-- Returns: 'above' | 'as_expected' | 'below' | 'too_few'
--
-- Returns 'too_few' for anything outside the REPORT band, i.e. below n = 30: -- not merely below the suppression floor. A funnel verdict is a comparison
-- against the programme rate, and the provisional band is defined as "never
-- used in a comparison or a ranking" (README §8.1). Returning 'as_expected'
-- for a partner with n = 20 would smuggle exactly that comparison back in.
--
-- WHAT THIS IS NOT: a ranking. Everything returning 'as_expected' is
-- indistinguishable on the evidence available. Do not sort by it, do not
-- colour a league table green-to-red with it, and do not put it in a partner's
-- performance review without the denominator beside it.

CREATE OR REPLACE FUNCTION rpt.funnel_verdict(
    p_numerator    integer,
    p_denominator  integer,
    p_overall_rate numeric          -- as a proportion, 0..1
)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    WITH s AS (
        SELECT
            p_denominator::numeric AS n,
            p_overall_rate::numeric AS r,
            (SELECT funnel_z FROM rpt.reporting_parameters WHERE id = 1) AS z
    ),
    lim AS (
        SELECT
            r - z * sqrt(r * (1 - r) / n) AS lower,
            r + z * sqrt(r * (1 - r) / n) AS upper
        FROM s
        WHERE n > 0 AND r IS NOT NULL
    )
    SELECT CASE
        WHEN rpt.suppression_band(p_denominator) <> 'report' THEN 'too_few'
        WHEN (SELECT count(*) FROM lim) = 0                  THEN 'too_few'
        WHEN p_numerator::numeric / p_denominator < (SELECT lower FROM lim) THEN 'below'
        WHEN p_numerator::numeric / p_denominator > (SELECT upper FROM lim) THEN 'above'
        ELSE 'as_expected'
    END;
$$;

-- -----------------------------------------------------------------------------
-- rpt.verdict_label(verdict)
-- -----------------------------------------------------------------------------
-- Symbol AND word, never colour alone. WCAG 1.4.1.

CREATE OR REPLACE FUNCTION rpt.verdict_label(p_verdict text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE p_verdict
        WHEN 'above'       THEN '▲ above expected'
        WHEN 'below'       THEN '▼ below expected'
        WHEN 'as_expected' THEN '▬ as expected'
        ELSE                    '· too few to assess'
    END;
$$;

-- -----------------------------------------------------------------------------
-- rpt.age_band(date_of_birth, as_of)
-- -----------------------------------------------------------------------------
-- Ethiopia defines youth as 15-29, NOT the international 15-24. Confirmed in
-- the ILO Ethiopia Youth Country Brief (2023), the Ethiopian Statistical Service
-- 2013 EFY Labour Force Survey, and the Federal Plan of Action for Job Creation.
-- The 15-17 / 18-24 splits are the ILO-recommended subgroups and are needed for
-- international comparability.

CREATE OR REPLACE FUNCTION rpt.age_band(p_dob date, p_as_of date DEFAULT current_date)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_dob IS NULL THEN 'unknown'
        ELSE (
            SELECT CASE
                WHEN a < 15 THEN 'under 15'
                WHEN a < 18 THEN '15-17'
                WHEN a < 25 THEN '18-24'
                WHEN a < 30 THEN '25-29'
                ELSE '30+'
            END
            FROM (SELECT extract(year FROM age(p_as_of, p_dob))::integer AS a) t
        )
    END;
$$;

-- -----------------------------------------------------------------------------
-- rpt.is_mature(reference_date, days_required, as_of)
-- -----------------------------------------------------------------------------
-- The maturation guard. A referral raised three days before period end is not an
-- unclosed loop, and a youth placed 20 days ago is not a 30-day retention
-- failure. Every checkpoint metric MUST filter its denominator on this.
--
-- Omitting it does two things, both bad: rates collapse at every period
-- boundary, and staff learn to stop raising referrals late in the quarter.

CREATE OR REPLACE FUNCTION rpt.is_mature(
    p_reference_date date,
    p_days_required  integer,
    p_as_of          date DEFAULT current_date
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_reference_date IS NOT NULL
       AND p_reference_date + p_days_required <= p_as_of;
$$;

CREATE OR REPLACE FUNCTION rpt.matures_on(p_reference_date date, p_days_required integer)
RETURNS date
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_reference_date + p_days_required;
$$;

COMMENT ON FUNCTION rpt.matures_on(date, integer) IS
  'The date a cell becomes scoreable. Render this in not-yet-due cells instead of a blank '
  'or a zero: a blank reads as programme collapse in a donor review.';
