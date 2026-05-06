import { CorporateAction } from "../hooks/useCorpAct";

interface Props {
  events: CorporateAction[];
}

export default function UpcomingFeed({ events }: Props) {
  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {events.slice(0, 10).map((e) => (
        <div
          key={e.id}
          className="flex-shrink-0 bg-white border border-gray-200 rounded-lg px-4 py-3 min-w-[160px]"
        >
          <p className="font-mono text-sm font-medium text-gray-900">{e.ticker}</p>
          <p className="text-xs text-gray-500 capitalize">{e.event_type}</p>
          <p className="text-xs text-gray-400 mt-1">{e.ex_date}</p>
          {e.amount != null && (
            <p className="text-sm font-medium text-green-700 mt-1">
              {e.currency} {e.amount.toFixed(2)}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
