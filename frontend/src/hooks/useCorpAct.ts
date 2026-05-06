import useSWR from "swr";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export interface CorporateAction {
  id: string;
  ticker: string;
  company_name: string | null;
  event_type: string;
  ex_date: string | null;
  record_date: string | null;
  pay_date: string | null;
  amount: number | null;
  currency: string | null;
  ratio: number | null;
  source: string;
  created_at: string;
}

export interface EventsResponse {
  items: CorporateAction[];
  total: number;
  page: number;
  page_size: number;
}

export interface TickerSummary {
  ticker: string;
  company_name: string | null;
  event_count: number;
  latest_event_date: string | null;
}

export function useEvents(params: Record<string, string | number | undefined> = {}) {
  const query = new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)])
  ).toString();
  const url = `${API_URL}/api/events${query ? `?${query}` : ""}`;
  return useSWR<EventsResponse>(url, fetcher, { refreshInterval: 60_000 });
}

export function useUpcoming(days = 30) {
  return useSWR<CorporateAction[]>(
    `${API_URL}/api/events/upcoming?days=${days}`,
    fetcher,
    { refreshInterval: 300_000 }
  );
}

export function useTickers() {
  return useSWR<TickerSummary[]>(`${API_URL}/api/tickers`, fetcher, {
    refreshInterval: 300_000,
  });
}

export function exportCsvUrl(params: Record<string, string> = {}): string {
  const query = new URLSearchParams(params).toString();
  return `${API_URL}/api/events/export${query ? `?${query}` : ""}`;
}
