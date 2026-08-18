import { App } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../../api/client";

/**
 * One fetch, shared by the four tiers.
 *
 * Each tier is a separate endpoint rather than one fat payload, for the same
 * reason the handoff caps cards per tier: nobody should pay for the donor's
 * disaggregation while opening their own work queue, and the brief's users are
 * on 3G.
 */
export function useTier<T>(path: string) {
  const { message } = App.useApp();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData((await api.get<T>(path)).data);
    } catch (error) {
      message.error(errorMessage(error, "Could not load this dashboard."));
    } finally {
      setLoading(false);
    }
  }, [path, message]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, loading, reload: load };
}
