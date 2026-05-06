import { CorporateAction } from "../hooks/useCorpAct";

const EVENT_COLORS: Record<string, string> = {
  dividend:     "bg-green-100 text-green-800",
  split:        "bg-blue-100 text-blue-800",
  merger:       "bg-purple-100 text-purple-800",
  spinoff:      "bg-amber-100 text-amber-800",
  rights_issue: "bg-pink-100 text-pink-800",
  name_change:  "bg-gray-100 text-gray-700",
};

interface Props {
  events: CorporateAction[];
}

export default function EventsTable({ events }: Props) {
  if (!events.length) {
    return <p className="text-sm text-gray-400 py-8 text-center">No events found.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 text-left text-xs text-gray-500 uppercase tracking-wide">
            <th className="px-4 py-3 font-medium">Ticker</th>
            <th className="px-4 py-3 font-medium">Company</th>
            <th className="px-4 py-3 font-medium">Type</th>
            <th className="px-4 py-3 font-medium">Ex-date</th>
            <th className="px-4 py-3 font-medium">Amount / ratio</th>
            <th className="px-4 py-3 font-medium">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {events.map((e) => (
            <tr key={e.id} className="hover:bg-gray-50 transition-colors">
              <td className="px-4 py-3 font-mono font-medium text-gray-900">{e.ticker}</td>
              <td className="px-4 py-3 text-gray-600 truncate max-w-xs">{e.company_name ?? "—"}</td>
              <td className="px-4 py-3">
                <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${EVENT_COLORS[e.event_type] ?? "bg-gray-100 text-gray-700"}`}>
                  {e.event_type}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-600">{e.ex_date ?? "—"}</td>
              <td className="px-4 py-3 text-gray-600">
                {e.amount != null
                  ? `${e.currency ?? ""} ${e.amount.toFixed(4)}`
                  : e.ratio != null
                  ? `${e.ratio}:1`
                  : "—"}
              </td>
              <td className="px-4 py-3 text-gray-400 text-xs">{e.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
