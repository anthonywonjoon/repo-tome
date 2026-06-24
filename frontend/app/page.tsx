"use client";

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";

const API = "http://localhost:8000";

type Source = {
  file: string;
  start_line: number;
  end_line: number;
  name: string;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
};

type Repo = {
  name: string;
  status: string;
  chunks: number;
};

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [activeRepo, setActiveRepo] = useState<string | null>(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [indexing, setIndexing] = useState(false);
  const [indexingName, setIndexingName] = useState("")
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mounted, setMounted] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setMounted(true);
    fetchRepos();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function fetchRepos() {
    try {
      const res = await fetch(`${API}/repos`);
      const data = await res.json();
      setRepos(data.repos || []);

      if (!activeRepo && data.repos?.length > 0) {
        setActiveRepo(data.repos[0].name);
      }
    } catch {
      // fix later
    }
  }

  function selectRepo(name: string) {
    if (name === activeRepo) return;
    setActiveRepo(name);
    setMessages([]);
    setError("");
  }

  async function handleIngest() {
    if (!repoUrl.trim() || indexing) return;
    setError("");

    const name = repoUrl.trim().replace(".git", "").split("/").pop() || "";
    setIndexingName(name);
    setIndexing(true);

    try {
      const res = await fetch(`${API}/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repoUrl.trim() }),
      });

      if (!res.ok) {
        const data = await res.json();

        if (res.status === 409) {
          setActiveRepo(name);
          setMessages([]);
          setIndexing(false);
          setRepoUrl("");
          await fetchRepos();
          return;
        }
        throw new Error(data.detail || "Ingest failed");
      }

      pollRef.current = setInterval(async () => {
        const statusRes = await fetch(`${API}/repos/${name}/status`);
        const statusData = await statusRes.json();

        if (statusData.status === "ready") {
          clearInterval(pollRef.current!);
          setIndexing(false);
          setActiveRepo(name);
          setRepoUrl("");
          setMessages([{
            role: "assistant",
            content: `**${name}** is indexed and ready — ${(await (await fetch(`${API}/repos`)).json()).repos.find((r: Repo) => r.name === name)?.chunks ?? "?"} chunks. Ask me anything about the codebase.`,
          }]);
          await fetchRepos();
        } else if (statusData.status?.startsWith("error")) {
          clearInterval(pollRef.current!);
          setIndexing(false);
          setError(statusData.status.replace("error: ", ""));
        }
      }, 2500);
    } catch (e: unknown) {
      setIndexing(false);
      setError(e instanceof Error ? e.message : "Something went wrong");
    }
  }

  async function handleAsk() {
    if (!question.trim() || loading || !activeRepo) return;
    setError("");

    const userMessage: Message = { role: "user", content: question };
    setMessages((prev) => [...prev, userMessage]);
    setQuestion("");
    setLoading(true);

    try {
      const res = await fetch(`${API}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_name: activeRepo, question: question.trim() }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Query failed");
      }

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer, sources: data.sources }
      ]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const TomeIcon = ({ size = 20 }: { size?: number }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="3" width="13" height="18" rx="2" fill="#2a2a2a" stroke="#444" strokeWidth="0.75" />
      <rect x="6" y="3" width="13" height="18" rx="2" fill="#1e1e1e" stroke="#3a3a3a" strokeWidth="0.75" />
      <line x1="9" y1="8" x2="16" y2="8" stroke="#555" strokeWidth="0.75" strokeLinecap="round" />
      <line x1="9" y1="11" x2="16" y2="11" stroke="#555" strokeWidth="0.75" strokeLinecap="round" />
      <line x1="9" y1="14" x2="13" y2="14" stroke="#555" strokeWidth="0.75" strokeLinecap="round" />
      <path d="M6 20 Q12 18 19 20" stroke="#666" strokeWidth="0.75" fill="none" strokeLinecap="round" />
    </svg>
  );

  if (!mounted) return null;

   return (
    <main className="flex flex-col h-[100dvh] bg-[#111] text-[#d8d8d8] font-sans overflow-hidden">

      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3 border-b border-[#2a2a2a] bg-[#111] flex-shrink-0">
        <div className="flex items-center gap-2">
          <TomeIcon size={20} />
          <span className="text-[14px] font-medium text-[#e8e8e8] tracking-tight">repo-tome</span>
        </div>
        <span className="text-[11px] text-[#3a3a3a]">
          {repos.length > 0 ? `${repos.length} repo${repos.length !== 1 ? "s" : ""} indexed` : "no repos indexed"}
        </span>
      </header>

      {/* Recently indexed repos shelf */}
      {repos.length > 0 && (
        <div className="flex items-center gap-2 px-5 py-2 border-b border-[#222] bg-[#0e0e0e] overflow-x-auto scrollbar-none flex-shrink-0">
          <span className="text-[10px] text-[#3a3a3a] uppercase tracking-widest flex-shrink-0">Recent</span>
          {repos.map((repo) => (
            <button
              key={repo.name}
              onClick={() => selectRepo(repo.name)}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] border flex-shrink-0 transition-colors ${
                activeRepo === repo.name
                  ? "bg-[#1e1e1e] border-[#3a3a3a] text-[#ccc]"
                  : "bg-[#171717] border-[#2a2a2a] text-[#666] hover:border-[#3a3a3a] hover:text-[#aaa]"
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${activeRepo === repo.name ? "bg-green-500" : "bg-[#444]"}`} />
              {repo.name}
            </button>
          ))}
        </div>
      )}
      {/* Index new repo */}
      <div className="flex items-center gap-2 px-5 py-2 border-b border-[#222] bg-[#0e0e0e] flex-shrink-0">
        <div className="flex gap-2 w-full max-w-full">
          <input
            className="flex-1 bg-[#1c1c1c] border border-[#2e2e2e] rounded-lg px-3.5 py-1.5 text-[12px] text-[#888] placeholder-[#3a3a3a] outline-none focus:border-[#3a3a3a] transition-colors disabled:opacity-40"
            placeholder="https://github.com/owner/repo"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleIngest()}
            disabled={indexing ? true : false}
          />
          <button
            onClick={handleIngest}
            disabled={(indexing || !repoUrl.trim()) ? true : false}
            className="bg-[#1c1c1c] border border-[#2e2e2e] rounded-lg px-3.5 py-1.5 text-[12px] font-medium text-[#888] hover:border-[#3a3a3a] hover:text-[#aaa] disabled:opacity-40 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            {indexing ? "Indexing…" : "Index repo"}
          </button>
        </div>
      </div>

      {/* Chat body */}
      <div className="flex-1 overflow-y-auto flex flex-col items-center px-4">
        {messages.length === 0 && !indexing ? (
          /* Empty state */
          <div className="flex flex-col items-center justify-center flex-1 gap-4 py-16">
            <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
              <rect x="8" y="6" width="34" height="50" rx="4" fill="#232323" stroke="#3a3a3a" strokeWidth="1" />
              <rect x="14" y="6" width="34" height="50" rx="4" fill="#1a1a1a" stroke="#333" strokeWidth="1" />
              <line x1="21" y1="18" x2="41" y2="18" stroke="#444" strokeWidth="1.5" strokeLinecap="round" />
              <line x1="21" y1="24" x2="41" y2="24" stroke="#444" strokeWidth="1.5" strokeLinecap="round" />
              <line x1="21" y1="30" x2="41" y2="30" stroke="#444" strokeWidth="1.5" strokeLinecap="round" />
              <line x1="21" y1="36" x2="33" y2="36" stroke="#444" strokeWidth="1.5" strokeLinecap="round" />
              <path d="M14 54 Q32 49 48 54" stroke="#555" strokeWidth="1.5" fill="none" strokeLinecap="round" />
            </svg>
            <p className="text-[18px] font-medium text-[#ccc] tracking-tight">
              {activeRepo ? `Ask about ${activeRepo}` : "Ask your codebase anything"}
            </p>
            <p className="text-[12px] text-[#555] text-center max-w-[280px] leading-relaxed">
              {activeRepo
                ? "Ask a question below to get cited answers from the source code."
                : "Index a GitHub repo below, then ask questions and get cited answers."}
            </p>
          </div>
        ) : (
          /* Messages */
          <div className="w-full max-w-[640px] flex flex-col gap-5 py-6">
            {/* Indexing indicator */}
            {indexing && (
              <div className="flex items-center gap-3 text-[13px] text-[#555]">
                <span className="animate-pulse">⏳</span>
                Indexing <span className="text-[#888]">{indexingName}</span> — this takes a minute or two…
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-2.5 items-start ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                {/* Avatar */}
                <div className={`w-6 h-6 rounded-full flex-shrink-0 flex items-center justify-center text-[10px] font-medium mt-0.5 border border-[#2e2e2e] ${msg.role === "assistant" ? "bg-[#1c1c1c]" : "bg-[#222]"}`}>
                  {msg.role === "assistant" ? <TomeIcon size={12} /> : <span className="text-[#888]">A</span>}
                </div>

                {/* Bubble */}
                <div className={`max-w-[calc(100%-38px)] text-[13px] leading-relaxed ${
                  msg.role === "user"
                    ? "bg-[#1e1e1e] border border-[#2e2e2e] rounded-2xl rounded-br-sm px-3.5 py-2.5 text-[#e0e0e0]"
                    : "text-[#d8d8d8] pt-0.5"
                }`}>
                  <div className="prose prose-invert prose-sm max-w-none">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>

                  {/* Sources */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-[#2a2a2a]">
                      <p className="text-[10px] font-medium text-[#444] uppercase tracking-widest mb-1.5">Sources</p>
                      <div className="flex flex-wrap gap-1">
                        {msg.sources.map((s, j) => (
                          <span key={j} className="inline-flex items-center gap-1 bg-[#141414] border border-[#2a2a2a] rounded-md px-2 py-1 font-mono text-[10px] text-[#666]">
                            <span className="text-[#aaa]">{s.file}</span>
                            {s.name && <span className="text-[#4a9eff]">({s.name})</span>}
                            <span className="text-[#444]">:{s.start_line}–{s.end_line}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Loading bubble */}
            {loading && (
              <div className="flex gap-2.5 items-start">
                <div className="w-6 h-6 rounded-full flex-shrink-0 flex items-center justify-center border border-[#2e2e2e] bg-[#1c1c1c] mt-0.5">
                  <TomeIcon size={12} />
                </div>
                <div className="text-[13px] text-[#444] pt-1">
                  <span className="animate-pulse">Searching the codebase…</span>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex-shrink-0 mx-4 mb-2">
          <div className="max-w-[640px] mx-auto text-[12px] text-red-400 bg-red-950/40 border border-red-900/50 rounded-lg px-3.5 py-2">
            {error}
          </div>
        </div>
      )}

      {/* Footer input */}
      <div className="flex-shrink-0 px-4 pb-5 pt-3 border-t border-[#2a2a2a] bg-[#111] flex flex-col items-center gap-2">

        {/* Question input */}
        <div className="w-full max-w-[640px] flex gap-2 items-center">
          <input
            className="flex-1 bg-[#1c1c1c] border border-[#2e2e2e] rounded-xl px-4 py-2.5 text-[13px] text-[#d8d8d8] placeholder-[#444] outline-none focus:border-[#3a3a3a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            placeholder={activeRepo ? "Ask anything about this codebase…" : "Index a repo first…"}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
            disabled={(!activeRepo || loading || indexing) ? true : false}
          />
          <button
            onClick={handleAsk}
            disabled={(!activeRepo || !question.trim() || loading || indexing) ? true : false}
            className="w-9 h-9 rounded-lg bg-[#e8e8e8] flex items-center justify-center flex-shrink-0 hover:bg-white disabled:opacity-30 disabled:cursor-not-allowed transition-opacity"
          >
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <path d="M8 13V3M3 8l5-5 5 5" stroke="#111" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        <span className="text-[10px] text-[#333]">Indexing takes ~1–2 min · answers cite exact file and line</span>
      </div>
    </main>
  );

}