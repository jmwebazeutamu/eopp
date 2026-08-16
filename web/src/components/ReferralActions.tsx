import { Alert, App, DatePicker, Form, Input, Modal, Select, Typography } from "antd";
import dayjs from "dayjs";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, errorMessage } from "../api/client";
import type {
  OutcomeTypeTerm,
  Paginated,
  Partner,
  Referral,
  ReferralCategoryTerm,
  TaxonomyTerm,
} from "../api/types";

/**
 * Everything that acts on a referral — spec §6.2.
 *
 * Shared by the case screen's stack panel and the cross-case referral queue.
 * Both surfaces offer the same moves against the same rules, so the mapping
 * from a referral's state to the buttons it offers lives here once. It is
 * derived from `allowed_transitions`, which the server computes from the §6.2
 * table, so neither screen can drift from the real state machine.
 */

export type ActionKind =
  | "initiate"
  | "confirm"
  | "decline"
  | "complete"
  | "fail"
  | "cancel"
  | "onward"
  | "replace";

export const ACTION_LABELS: Record<ActionKind, string> = {
  initiate: "New referral",
  confirm: "Partner confirmed",
  decline: "Partner declined",
  complete: "Record outcome",
  fail: "Record failure",
  cancel: "Withdraw referral",
  onward: "Onward referral",
  replace: "Replacement referral",
};

/** Actions that create a new referral, and so need a category and a partner. */
const CREATES_REFERRAL: ActionKind[] = ["initiate", "onward", "replace"];

/** The §6.2 moves this referral currently offers a user who may write. */
export function actionsFor(referral: Referral, canWrite: boolean): ActionKind[] {
  if (!canWrite) return [];
  const allowed = referral.allowed_transitions;
  const kinds: ActionKind[] = [];
  if (allowed.includes("ACTIVE")) kinds.push("confirm");
  if (referral.status === "PENDING_CONFIRMATION" && allowed.includes("FAILED")) kinds.push("decline");
  if (allowed.includes("CANCELLED")) kinds.push("cancel");
  if (allowed.includes("COMPLETED")) kinds.push("complete");
  if (referral.status === "ACTIVE" && allowed.includes("FAILED")) kinds.push("fail");
  // Onward and replacement create a *new* referral rather than moving this one,
  // so they are not in allowed_transitions.
  if (referral.status === "COMPLETED") kinds.push("onward");
  if (referral.status === "FAILED") kinds.push("replace");
  return kinds;
}

export interface ReferralTaxonomy {
  categories: ReferralCategoryTerm[];
  outcomeTypes: OutcomeTypeTerm[];
  failureReasons: TaxonomyTerm[];
}

const EMPTY_TAXONOMY: ReferralTaxonomy = { categories: [], outcomeTypes: [], failureReasons: [] };

/**
 * The §5 lookup tables.
 *
 * Fetched rather than hardcoded because §9 makes these configuration the system
 * administrator owns: a term added in the admin has to appear here without a
 * deploy. Retired terms stay off the list but remain on historical referrals.
 */
export function useReferralTaxonomy(): ReferralTaxonomy {
  const [taxonomy, setTaxonomy] = useState<ReferralTaxonomy>(EMPTY_TAXONOMY);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [categories, outcomes, failures] = await Promise.all([
          api.get<ReferralCategoryTerm[]>("/referrals/categories/"),
          api.get<OutcomeTypeTerm[]>("/referrals/outcome-types/"),
          api.get<TaxonomyTerm[]>("/referrals/failure-reasons/"),
        ]);
        if (!cancelled) {
          setTaxonomy({
            categories: categories.data,
            outcomeTypes: outcomes.data,
            failureReasons: failures.data,
          });
        }
      } catch {
        // Leaving the lists empty is enough: the selects then say so, and the
        // API rejects a write with no category anyway.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return taxonomy;
}

/**
 * Partners that can actually receive a referral, narrowed to a woreda.
 *
 * page_size: `can_receive_referrals` combines active status with MOU state and
 * is filtered client-side, so a truncated first page could hide every partner
 * that can serve this case.
 */
function usePartnerOptions(woreda: string | undefined, enabled: boolean) {
  const [partners, setPartners] = useState<Partner[]>([]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    void (async () => {
      try {
        const response = await api.get<Paginated<Partner>>("/partners/", {
          params: { woreda, page_size: 500 },
        });
        if (!cancelled) setPartners(response.data.results.filter((p) => p.can_receive_referrals));
      } catch {
        // The select renders empty; the form cannot be submitted without one.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [woreda, enabled]);

  return useMemo(
    () =>
      partners.map((p) => ({
        value: p.id,
        label: `${p.partner_name} (${p.partner_type_display})`,
      })),
    [partners],
  );
}

export interface ReferralAction {
  kind: ActionKind;
  /** Null only for `initiate`, which has no referral yet. */
  referral: Referral | null;
}

interface Props {
  action: ReferralAction | null;
  /** The case to initiate against. Required for `initiate`, ignored otherwise. */
  caseId?: string;
  /**
   * Woreda used to narrow the partner list. The case screen passes the case's;
   * the cross-case queue reads it off the referral being acted on.
   */
  woreda?: string;
  onClose: () => void;
  onDone: () => void;
}

/** Turns dayjs values into the plain dates DRF's DateField expects. */
function serialise(values: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(values)
      .filter(([, value]) => value !== undefined && value !== "")
      .map(([key, value]) => [key, dayjs.isDayjs(value) ? value.format("YYYY-MM-DD") : value]),
  );
}

/**
 * One modal for every §6.2 move.
 *
 * Every transition posts to `/referrals/{id}/{kind}/` and every creation to
 * `/referrals/initiate/` or `/referrals/{id}/{onward,replace}/`, so a single
 * handler covers all of them; only the fields differ.
 */
export default function ReferralActionModal({ action, caseId, woreda, onClose, onDone }: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  const { categories, outcomeTypes, failureReasons } = useReferralTaxonomy();
  const needsPartner = !!action && CREATES_REFERRAL.includes(action.kind);
  const partnerOptions = usePartnerOptions(woreda, needsPartner);

  // §5.1/§5.3/§5.4 mark some terms — the "Other" catch-alls — as requiring a
  // free-text note, and the backend rejects the write without one. Watching the
  // selection lets the form say so up front instead of surfacing a 400 after
  // the user has already submitted.
  const selectedCategory = Form.useWatch("referral_category", form) as string | undefined;
  const selectedOutcome = Form.useWatch("outcome_type", form) as string | undefined;
  const selectedFailure = Form.useWatch("failure_reason_code", form) as string | undefined;

  const noteRequired =
    categories.some((c) => c.code === selectedCategory && c.requires_note) ||
    outcomeTypes.some((o) => o.code === selectedOutcome && o.requires_note) ||
    failureReasons.some((f) => f.code === selectedFailure && f.requires_note);

  const noteRules = noteRequired ? [{ required: true, message: "This selection requires a note." }] : [];

  // §5.3 maps each outcome to the categories it applies to; an outcome with no
  // mapping applies everywhere. Offering one that does not apply would fail the
  // model's own check on save.
  const outcomeOptions = useMemo(() => {
    const category = action?.referral?.referral_category;
    return outcomeTypes
      .filter((o) => o.applies_to.length === 0 || (category ? o.applies_to.includes(category) : true))
      .map((o) => ({ value: o.code, label: o.label }));
  }, [outcomeTypes, action]);

  const categoryOptions = useMemo(
    () => categories.map((c) => ({ value: c.code, label: c.label })),
    [categories],
  );

  const submit = useCallback(
    async (values: Record<string, unknown>) => {
      if (!action) return;
      const payload = serialise(values);
      setSubmitting(true);
      try {
        if (action.kind === "initiate") {
          await api.post("/referrals/initiate/", { ...payload, case: caseId });
        } else {
          await api.post(`/referrals/${action.referral?.id}/${action.kind}/`, payload);
        }
        message.success(`${ACTION_LABELS[action.kind]} recorded.`);
        form.resetFields();
        onClose();
        onDone();
      } catch (error) {
        message.error(errorMessage(error, "Could not record that."));
      } finally {
        setSubmitting(false);
      }
    },
    [action, caseId, form, message, onClose, onDone],
  );

  return (
    <Modal
      open={!!action}
      title={action ? ACTION_LABELS[action.kind] : ""}
      okText="Save"
      confirmLoading={submitting}
      onCancel={() => {
        form.resetFields();
        onClose();
      }}
      onOk={() => form.submit()}
      destroyOnHidden
    >
      {action?.referral && (
        <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
          {action.referral.referral_category_label} for {action.referral.youth_name} ·{" "}
          {action.referral.receiving_partner_detail.partner_name}
        </Typography.Paragraph>
      )}

      <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
        {(action?.kind === "onward" || action?.kind === "replace") && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={
              action.kind === "onward"
                ? "The completed referral stays as it is; this creates the next one in the chain."
                : "The failed referral moves to Replaced and this becomes its replacement."
            }
          />
        )}

        {action?.kind === "cancel" && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="Withdrawing is not the same as a partner declining"
            description={
              "Cancelled is kept separate from Failed so the §8 partner performance figures do not " +
              "count a withdrawal against the partner. No replacement is prompted."
            }
          />
        )}

        {needsPartner && (
          <>
            <Form.Item name="referral_category" label="Category" rules={[{ required: true }]}>
              <Select options={categoryOptions} placeholder="What is this referral for?" />
            </Form.Item>
            <Form.Item
              name="receiving_partner"
              label="Receiving partner"
              rules={[{ required: true }]}
              extra={woreda ? `Active partners covering ${woreda}.` : undefined}
            >
              <Select
                options={partnerOptions}
                showSearch
                optionFilterProp="label"
                notFoundContent="No active partner covers this woreda."
              />
            </Form.Item>
            <Form.Item name="receiving_contact_name" label="Contact at the partner">
              <Input />
            </Form.Item>
          </>
        )}

        {action?.kind === "confirm" && (
          <>
            <Form.Item name="confirmed_by" label="Confirmed by" rules={[{ required: true }]}>
              <Input placeholder="Name of the partner contact who confirmed" />
            </Form.Item>
            <Form.Item name="confirmed_date" label="Date confirmed" extra="Leave blank for today.">
              <DatePicker style={{ width: "100%" }} maxDate={dayjs()} />
            </Form.Item>
          </>
        )}

        {(action?.kind === "decline" || action?.kind === "fail") && (
          <Form.Item name="failure_reason_code" label="Failure reason" rules={[{ required: true }]}>
            <Select options={failureReasons.map((f) => ({ value: f.code, label: f.label }))} />
          </Form.Item>
        )}

        {action?.kind === "fail" && (
          <Form.Item name="failure_date" label="Date it failed" extra="Leave blank for today.">
            <DatePicker style={{ width: "100%" }} maxDate={dayjs()} />
          </Form.Item>
        )}

        {action?.kind === "complete" && (
          <>
            <Form.Item
              name="outcome_type"
              label="Outcome"
              rules={[{ required: true }]}
              extra={
                outcomeOptions.length === 0
                  ? "No outcome type is configured for this referral category. An administrator must map one (spec §5.3)."
                  : undefined
              }
            >
              <Select options={outcomeOptions} notFoundContent="No outcome type applies to this category." />
            </Form.Item>
            <Form.Item name="outcome_date" label="Date of the outcome" extra="Leave blank for today.">
              <DatePicker style={{ width: "100%" }} maxDate={dayjs()} />
            </Form.Item>
            <Form.Item name="outcome_verification_method" label="How was it verified?">
              <Input placeholder="e.g. Follow-up home visit" />
            </Form.Item>
          </>
        )}

        <Form.Item
          name="notes"
          label="Notes"
          rules={noteRules}
          extra={noteRequired ? "This selection requires a note." : undefined}
        >
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
