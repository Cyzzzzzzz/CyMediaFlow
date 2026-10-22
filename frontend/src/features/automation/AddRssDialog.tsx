import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { automationApi } from "./api";
import { AutomationDialog } from "./AutomationDialog";
import { SubscriptionFields } from "./SubscriptionFields";
import { emptySubscription, validSubscription } from "./subscriptionForm";
import type { FeedCandidate } from "./types";

export function AddRssDialog({ onClose, onSuccess }: { onClose: () => void; onSuccess: (message: string) => void }) {
  const client = useQueryClient();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [parser, setParser] = useState<"bangumi" | "tmdb" | "parser">("bangumi");
  const [aggregate, setAggregate] = useState(false);
  const [candidates, setCandidates] = useState<FeedCandidate[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [active, setActive] = useState(0);
  const [step, setStep] = useState<"input" | "confirm">("input");
  const analyze = useMutation({ mutationFn: () => automationApi.analyze({ url: url.trim(), parser }), onSuccess: (result) => {
    setCandidates(result.candidates.map((item) => ({ ...item, rule: { ...emptySubscription(), ...item.rule } })));
    setSelected(result.candidates.length ? [0] : []); setActive(0); setStep("confirm");
  } });
  const subscribe = useMutation({ mutationFn: () => automationApi.subscribe({ url: url.trim(), name: name.trim(), rules: selected.map((index) => candidates[index].rule) }), onSuccess: (result) => {
    void client.invalidateQueries({ queryKey: ["automation"] });
    onSuccess(`已新增 ${result.created} 条追番规则${result.created < selected.length ? "，重复规则已保留" : ""}。${result.automation_enabled ? "将按 RSS 源与规则的启用状态定时检查。" : "自动追番尚未开启，请在设置页配置下载器并启用。"}`);
  } });
  const current = candidates[active];
  const busy = analyze.isPending || subscribe.isPending;
  const error = analyze.error ?? subscribe.error;
  return <AutomationDialog title="新增 RSS 订阅" onClose={onClose} busy={busy} footer={<>
    <span className="automation-note">{step === "input" ? "01 / 02 · 解析订阅" : "02 / 02 · 确认追番规则"}</span>
    <div className="subscription-footer-actions">{step === "confirm" ? <button type="button" className="secondary-button" onClick={() => { setStep("input"); subscribe.reset(); }} disabled={busy}>上一步</button> : null}<button type="button" className="primary-button" disabled={busy || (step === "input" ? !url.trim() : !selected.length || selected.some((index) => !validSubscription(candidates[index].rule)))} onClick={() => step === "input" ? analyze.mutate() : subscribe.mutate()}>{analyze.isPending ? "解析中…" : subscribe.isPending ? "保存中…" : step === "input" ? "解析 RSS" : `确认订阅${aggregate && selected.length ? `（${selected.length}）` : ""}`}</button></div>
  </>}>
    <fieldset className="subscription-fieldset" disabled={busy}>
      {step === "input" ? <div className="automation-form">
        <p className="automation-note">粘贴番剧 RSS，先预览识别结果，再确认订阅。解析不会添加下载任务。</p>
        <label>RSS 地址<input type="url" autoComplete="off" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…/RSS/Bangumi?…" /></label>
        <label>订阅名称<input value={name} onChange={(e) => setName(e.target.value)} placeholder="可不填，默认使用作品标题" maxLength={200} /></label>
        <label>识别来源<select value={parser} onChange={(e) => setParser(e.target.value as typeof parser)}><option value="bangumi">Bangumi</option><option value="tmdb">TMDB</option><option value="parser">仅解析发布标题</option></select></label>
        <label className="automation-check"><input type="checkbox" checked={aggregate} onChange={(e) => setAggregate(e.target.checked)} />聚合 RSS（一个源包含多部番剧）</label>
        <p className="automation-note">聚合源会列出已识别的作品供你勾选，不会自动订阅其他新作品。全局代理和下载器在设置页配置。</p>
      </div> : <>
        <div className="subscription-analysis-summary"><strong>{name || "RSS 解析结果"}</strong><span>{analyze.data?.total_entries ?? 0} 条发布 · {candidates.length} 组规则{analyze.data?.unrecognized ? ` · ${analyze.data.unrecognized} 条无法安全识别` : ""}</span></div>
        {analyze.data?.truncated ? <p className="automation-note">本次只显示前 30 组，请使用更具体的 RSS 地址筛选。</p> : null}
        {candidates.length > 1 ? <div className="subscription-candidate-list" aria-label="解析出的追番规则">{candidates.map((candidate, index) => <div key={index} className={index === active ? "selected" : ""}>{aggregate ? <input type="checkbox" aria-label={`订阅 ${candidate.rule.source_title} ${candidate.rule.preferred_group ?? ""}`} checked={selected.includes(index)} onChange={(e) => setSelected(e.target.checked ? [...selected, index] : selected.filter((id) => id !== index))} /> : <input type="radio" name="rss-rule" aria-label={`订阅 ${candidate.rule.source_title} ${candidate.rule.preferred_group ?? ""}`} checked={selected.includes(index)} onChange={() => { setSelected([index]); setActive(index); }} />}<button type="button" onClick={() => { setActive(index); if (!aggregate) setSelected([index]); }}><strong>{candidate.rule.title}</strong><span>Season {candidate.rule.season} · {candidate.rule.preferred_group ?? "未知字幕组"} · {candidate.rule.preferred_resolution ?? "未知清晰度"} · {candidate.entry_count} 条</span></button></div>)}</div> : null}
        {current ? <>
          {current.batch_count ? <p className="automation-note" role="status">识别到 {current.batch_count} 条合集{current.episode_ranges?.length ? `：${current.episode_ranges.map((range) => `${range.season === null ? "" : `S${String(range.season).padStart(2, "0")}`}E${String(range.start).padStart(2, "0")}–E${String(range.end).padStart(2, "0")}`).join("、")}` : ""}。{current.rule.allow_batch ? "已为本次草稿开启允许合集，可在高级设置关闭；下载后按每个视频的集号整理。" : "当前未允许合集，此类发布不会自动下载；可在高级设置开启。"}范围不代表季度总集数。</p> : null}
          {current.warning ? <p className="automation-note" role="status">{current.warning}</p> : null}
          <SubscriptionFields key={active} value={current.rule} matches={current.matches} onChange={(value) => setCandidates((old) => old.map((item, index) => index === active ? { ...item, rule: value } : item))} />
          <details className="subscription-section subscription-examples"><summary>发布样本 <span>{current.entry_count} 条</span></summary><div className="subscription-section-body">
            {current.versions?.length ? <p className="automation-note">修订版本：{current.versions.map((version) => `v${version}`).join(" / ")}（无标记按 v1 计）；字幕：{current.rule.subtitle || "未识别"}。同集修订版与语言版本共用规则，可在高级设置中筛选。</p> : null}
            {current.examples.map((example) => <p key={example}>{example}</p>)}
          </div></details>
          <p className="automation-note">确认后保存 RSS 和规则；启用自动追番时，下一轮检查会下载源内所有匹配且尚未提交的发布。多字幕组规则会分别生效，请只选择需要的版本。</p>
        </> : <div className="page-state">没有识别到可安全订阅的发布。支持单集及同季明确集数范围的合集；跨季或集号不明的资源请在 RSS 页保存源后手动检查。</div>}
      </>}
    </fieldset>
    {error ? <p role="alert" className="automation-note error">{error.message}</p> : null}
  </AutomationDialog>;
}
