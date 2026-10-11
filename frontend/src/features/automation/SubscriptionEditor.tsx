import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { automationApi } from "./api";
import { AutomationDialog } from "./AutomationDialog";
import { SubscriptionFields } from "./SubscriptionFields";
import { emptySubscription, validSubscription } from "./subscriptionForm";
import type { Feed, Subscription } from "./types";

export function SubscriptionEditor({ rule, feeds, siblings, onSelect, onClose, onDownloads }: {
  rule: Subscription | null; feeds: Feed[]; siblings: Subscription[];
  onSelect: (rule: Subscription) => void; onClose: () => void; onDownloads: (id: number) => void;
}) {
  const client = useQueryClient();
  const [form, setForm] = useState(() => ({ ...emptySubscription(), ...rule }));
  const [feedId, setFeedId] = useState(rule?.feed_id ?? feeds[0]?.id ?? 0);
  const [deleting, setDeleting] = useState(false);
  const success = () => { void client.invalidateQueries({ queryKey: ["automation"] }); onClose(); };
  const save = useMutation({ mutationFn: (archived: boolean) => automationApi.saveRule(rule?.id ?? null, { ...form, feed_id: feedId, archived }), onSuccess: success });
  const remove = useMutation({ mutationFn: () => automationApi.deleteRule(rule!.id), onSuccess: success });
  const busy = save.isPending || remove.isPending;
  const error = save.error ?? remove.error;
  const feed = feeds.find((item) => item.id === feedId);
  return <AutomationDialog title={rule ? "编辑追番规则" : "添加追番规则"} onClose={onClose} busy={busy} footer={<>
    {rule ? <button type="button" className="quiet-button danger-text" onClick={() => setDeleting(true)} disabled={busy}>删除规则</button> : null}
    <div className="subscription-footer-actions"><button type="button" className="secondary-button" onClick={onClose} disabled={busy}>取消</button><button type="button" className="primary-button" disabled={busy || !feedId || !validSubscription(form)} onClick={() => save.mutate(form.archived)}>{save.isPending ? "保存中…" : "应用修改"}</button></div>
  </>}>
    <fieldset className="subscription-fieldset" disabled={busy}>
      {siblings.length > 1 ? <label className="subscription-rule-picker">此番剧有 {siblings.length} 条规则<select value={rule?.id} onChange={(e) => onSelect(siblings.find((item) => item.id === Number(e.target.value))!)}>{siblings.map((item) => <option value={item.id} key={item.id}>{feeds.find((feed) => feed.id === item.feed_id)?.name ?? "已删除 RSS"} · {item.preferred_group ?? "不限字幕组"} · {item.preferred_resolution ?? "不限清晰度"}</option>)}</select></label> : null}
      <SubscriptionFields value={form} onChange={setForm} localPoster={form.poster_url === rule?.poster_url ? rule?.local_poster_url : null} />
      <div className="subscription-feed-row"><label>RSS 源<select value={feedId} onChange={(e) => setFeedId(Number(e.target.value))}>{!feed ? <option value={feedId}>请选择有效的 RSS 源</option> : null}{feeds.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><span title="隐藏地址中的订阅凭据">{feed?.url}</span></div>
      {rule ? <div className="subscription-secondary-actions"><button type="button" className="secondary-button" onClick={() => onDownloads(rule.id)}>查看下载任务</button><label className="automation-check"><input type="checkbox" checked={form.archived} onChange={(e) => setForm({ ...form, archived: e.target.checked })} />归档（停止接收新发布）</label></div> : null}
    </fieldset>
    {deleting ? <div className="subscription-delete-confirm" role="alert"><p>删除“{rule?.title}”的这条规则？只删除配置，不删除下载器任务或媒体文件。</p><button type="button" className="secondary-button" onClick={() => setDeleting(false)} disabled={busy}>保留规则</button><button type="button" className="secondary-button danger-text" onClick={() => remove.mutate()} disabled={busy}>确认删除规则</button></div> : null}
    {error ? <p role="alert" className="automation-note error">{error.message}</p> : null}
  </AutomationDialog>;
}
