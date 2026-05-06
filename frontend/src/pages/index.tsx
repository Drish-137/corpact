import { useState } from "react";
import { useEvents, useUpcoming, exportCsvUrl } from "../hooks/useCorpAct";
import EventsTable from "../components/EventsTable";
import UpcomingFeed from "../components/UpcomingFeed";

const EVENT_TYPES = ["", "dividend", "split", "merger", "spinoff", "rights_issue", "name_change"];

export default function Dashboard() {
  const [ticker, setTicker] = useState("");
  const [eventType, setEventType] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useEvents({
    ticker: ticker || undefined,
    event_type: eventType || undefined,
    page,
    page_size: 50,
  });

  const { data: upcoming } = useUpcoming(30);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-medium text-gray-900">corpact</h1>
            <p className="text-sm text-gray-500">Corporate actions — public financial data</p>
          </div>
          <a
            href={exportCsvUrl({ ticker, event_type: eventType })}
            className="text-sm px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Export CSV
          </a>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">

        {/* Upcoming events strip */}
        {upcoming && upcoming.length > 0 && (
          <section>
            <h2 className="text-sm font-medium text-gray-500 mb-3 uppercase tracking-wide">
              Upcoming (next 30 days)
            </h2>
            <UpcomingFeed events={upcoming} />
          </section>
        )}

        {/* Filters */}
        <section className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Ticker</label>
            <input
              className="border border-gray-300 rounded-md px-3 py-2 text-sm w-32 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="AAPL"
              value={ticker}
              onChange={(e) => { setTicker(e.target.value.toUpperCase()); setPage(1); }}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Event type</label>
            <select
              className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={eventType}
              onChange={(e) => { setEventType(e.target.value); setPage(1); }}
            >
              {EVENT_TYPES.map((t) => (
                <option key={t} value={t}>{t || "All types"}</option>
              ))}
            </select>
          </div>
          {(ticker || eventType) && (
            <button
              className="text-sm text-gray-500 hover:text-gray-700 underline"
              onClick={() => { setTicker(""); setEventType(""); setPage(1); }}
            >
              Clear filters
            </button>
          )}
        </section>

        {/* Events table */}
        <section>
          {isLoading && <p className="text-sm text-gray-400">Loading...</p>}
          {error && <p className="text-sm text-red-500">Failed to load events.</p>}
          {data && (
            <>
              <p className="text-xs text-gray-400 mb-2">{data.total.toLocaleString()} events</p>
              <EventsTable events={data.items} />
              <div className="flex gap-3 mt-4 items-center">
                <button
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                  className="text-sm px-3 py-1 border rounded-md disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="text-sm text-gray-500">Page {page}</span>
                <button
                  disabled={data.items.length < 50}
                  onClick={() => setPage((p) => p + 1)}
                  className="text-sm px-3 py-1 border rounded-md disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  );
}
