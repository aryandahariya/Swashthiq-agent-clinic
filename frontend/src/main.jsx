import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, AlertTriangle, CheckCircle2, ClipboardList, MessageSquare, PhoneForwarded, RefreshCw } from 'lucide-react';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function StatusBadge({ status, reason }) {
  return <span className={`status ${status}`}>{reason || status}</span>;
}

function Sidebar({ selected, onSelect, conversations }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <Activity size={24} />
        <div>
          <strong>SwasthiQ</strong>
          <span>Front Desk Agent</span>
        </div>
      </div>
      <button className={!selected ? 'nav active' : 'nav'} onClick={() => onSelect(null)}>
        <ClipboardList size={18} /> Handoff Queue
      </button>
      <div className="navGroup">
        {conversations.map((item) => (
          <button key={item.conversation_id} className={selected === item.conversation_id ? 'nav active' : 'nav'} onClick={() => onSelect(item.conversation_id)}>
            <MessageSquare size={16} /> {item.conversation_id}
          </button>
        ))}
      </div>
    </aside>
  );
}

function StatCard({ label, value, icon: Icon }) {
  return (
    <section className="stat">
      <Icon size={20} />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </section>
  );
}

function HandoffTable({ rows, onOpen, onResolve }) {
  if (!rows.length) {
    return <div className="empty">No open handoffs.</div>;
  }
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Conversation</th>
            <th>Caller Said</th>
            <th>Reason</th>
            <th>Time</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.conversation_id}>
              <td><button className="linkBtn" onClick={() => onOpen(row.conversation_id)}>{row.conversation_id}</button></td>
              <td>{row.script?.turns?.[0] || row.reply}</td>
              <td><StatusBadge status={row.terminal_state} reason={row.escalation_reason} /></td>
              <td>{row.metrics?.latency_ms ?? 0} ms</td>
              <td><button className="iconBtn" onClick={() => onResolve(row.conversation_id)} title="Resolve"><CheckCircle2 size={18} /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ToolCallCard({ call }) {
  return (
    <div className="toolCall">
      <div className="toolTitle">
        <RefreshCw size={15} />
        <strong>{call.name}</strong>
      </div>
      <pre>{JSON.stringify(call.arguments, null, 2)}</pre>
      {call.result && <pre>{JSON.stringify(call.result, null, 2)}</pre>}
    </div>
  );
}

function ConversationTranscript({ detail }) {
  const tools = detail.tool_call_details || detail.tool_calls || [];
  return (
    <section className="transcript">
      {(detail.script?.turns || []).map((turn, index) => (
        <React.Fragment key={index}>
          <div className="bubble caller">{turn}</div>
          {tools[index] && <ToolCallCard call={tools[index]} />}
        </React.Fragment>
      ))}
      {tools.slice((detail.script?.turns || []).length).map((call, index) => <ToolCallCard key={`extra-${index}`} call={call} />)}
      <div className="bubble agent">{detail.reply}</div>
    </section>
  );
}

function OutcomePanel({ detail }) {
  return (
    <aside className="outcome">
      <h2>Outcome</h2>
      <dl>
        <dt>Status</dt><dd><StatusBadge status={detail.terminal_state} reason={detail.escalation_reason} /></dd>
        <dt>Patient</dt><dd>{detail.patient_id || 'Unresolved'}</dd>
        <dt>Appointment</dt><dd>{detail.appointment_id || 'None'}</dd>
        <dt>Turns</dt><dd>{detail.metrics?.turns}</dd>
        <dt>Tokens</dt><dd>{detail.metrics?.tokens}</dd>
        <dt>Latency</dt><dd>{detail.metrics?.latency_ms} ms</dd>
      </dl>
    </aside>
  );
}

function Queue({ data, onOpen, onResolve }) {
  return (
    <main className="content">
      <header className="pageHeader">
        <div>
          <h1>Handoff Queue</h1>
          <p>{data.clinic} · Dehradun · Asia/Kolkata</p>
        </div>
      </header>
      <div className="stats">
        <StatCard label="Conversations" value={data.summary.total} icon={MessageSquare} />
        <StatCard label="Completed by Agent" value={data.summary.completed} icon={CheckCircle2} />
        <StatCard label="Escalated" value={data.summary.escalated} icon={PhoneForwarded} />
        <StatCard label="Urgent Clinical" value={data.summary.urgent} icon={AlertTriangle} />
      </div>
      <section className="panel">
        <h2>Open Handoffs</h2>
        <HandoffTable rows={data.handoffs} onOpen={onOpen} onResolve={onResolve} />
      </section>
    </main>
  );
}

function Detail({ id }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    setDetail(null);
    fetch(`${API}/api/conversations/${id}`)
      .then((res) => res.ok ? res.json() : Promise.reject(new Error('Could not load conversation')))
      .then(setDetail)
      .catch((err) => setError(err.message));
  }, [id]);
  if (error) return <main className="content"><div className="error">{error}</div></main>;
  if (!detail) return <main className="content"><div className="loading">Loading conversation...</div></main>;
  return (
    <main className="content detailGrid">
      <section>
        <header className="pageHeader">
          <div>
            <h1>{detail.conversation_id}</h1>
            <p>Sunrise Clinic · {detail.script?.today || '2026-10-01'} · {detail.terminal_state}</p>
          </div>
          <StatusBadge status={detail.terminal_state} reason={detail.escalation_reason} />
        </header>
        <ConversationTranscript detail={detail} />
      </section>
      <OutcomePanel detail={detail} />
    </main>
  );
}

function App() {
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const load = () => fetch(`${API}/api/handoffs`)
    .then((res) => res.ok ? res.json() : Promise.reject(new Error('Could not load handoffs')))
    .then(setData)
    .catch((err) => setError(err.message));
  useEffect(() => { load(); }, []);
  const conversations = useMemo(() => data?.conversations || [], [data]);
  const resolve = (id) => fetch(`${API}/api/handoffs/${id}/resolve`, { method: 'POST' }).then(load);
  if (error) return <div className="app"><div className="error">{error}</div></div>;
  if (!data) return <div className="app"><div className="loading">Loading handoff queue...</div></div>;
  return (
    <div className="app">
      <Sidebar selected={selected} onSelect={setSelected} conversations={conversations} />
      {selected ? <Detail id={selected} /> : <Queue data={data} onOpen={setSelected} onResolve={resolve} />}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
