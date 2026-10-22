import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { featureApi } from "./featureApi";
import { SubscriptionPoster } from "./SubscriptionPoster";
import type { Subscription } from "./types";
import "./calendar.css";

export function useAutomationEvents() {
  const client = useQueryClient();
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const stream = new EventSource("/api/v1/automation/stream");
    let timer: ReturnType<typeof setTimeout> | undefined;
    stream.addEventListener("update", () => {
      if (timer) return;
      timer = setTimeout(() => {
        timer = undefined;
        for (const key of ["downloads", "events", "notifications", "releases"])
          void client.invalidateQueries({ queryKey: ["automation", key] });
      }, 400);
    });
    return () => {
      stream.close();
      clearTimeout(timer);
    };
  }, [client]);
}

export function CalendarPanel({
  onEdit,
}: {
  onEdit: (rule: Subscription) => void;
}) {
  const client = useQueryClient();
  const calendar = useQuery({
    queryKey: ["automation", "calendar"],
    queryFn: featureApi.calendar,
  });
  const refresh = useMutation({
    mutationFn: featureApi.refreshCalendar,
    onSuccess: (data) => client.setQueryData(["automation", "calendar"], data),
  });
  return (
    <section className="automation-panel">
      <div className="automation-panel-head">
        <div>
          <h2>播出日历</h2>
          <p>展示正在追番的作品，手动设置的放送星期优先。</p>
        </div>
        <button
          className="secondary-button"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
        >
          更新 Bangumi 日历
        </button>
      </div>
      {refresh.error || calendar.error ? (
        <p role="alert" className="automation-note error">
          {(refresh.error ?? calendar.error)?.message}
        </p>
      ) : null}
      <div className="automation-calendar">
        {["周一", "周二", "周三", "周四", "周五", "周六", "周日", "待定"].map(
          (day, index) => (
            <section key={day} aria-labelledby={`calendar-day-${index}`}>
              <h3 id={`calendar-day-${index}`}>{day}</h3>
              {calendar.data?.items
                .filter((r) => (r.air_weekday ?? 7) === index)
                .map((rule) => (
                  <button
                    type="button"
                    className="calendar-anime"
                    key={rule.id}
                    aria-label={`编辑追番规则：${rule.title}`}
                    title={rule.title}
                    onClick={() => onEdit(rule)}
                  >
                    <SubscriptionPoster
                      title={rule.title}
                      url={rule.poster_url}
                      localUrl={rule.local_poster_url}
                    />
                    <span className="calendar-anime-title">{rule.title}</span>
                  </button>
                ))}
            </section>
          ),
        )}
      </div>
    </section>
  );
}

export function NotificationsPanel() {
  const client = useQueryClient();
  const inbox = useQuery({
    queryKey: ["automation", "notifications"],
    queryFn: featureApi.notifications,
  });
  const read = useMutation({
    mutationFn: () =>
      featureApi.markRead(
        Math.max(0, ...(inbox.data?.items.map((i) => i.id) ?? [])),
      ),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["automation", "notifications"] }),
  });
  return (
    <section className="automation-panel">
      <div className="automation-panel-head">
        <div>
          <h2>通知</h2>
          <p>{inbox.data?.unread ?? 0} 条未读</p>
        </div>
        <button
          className="secondary-button"
          onClick={() => read.mutate()}
          disabled={read.isPending}
        >
          全部标为已读
        </button>
      </div>
      <div className="automation-card-list">
        {inbox.data?.items.map((item) => (
          <article className="automation-card" key={item.id}>
            <div>
              <strong>
                {!item.read ? "• " : ""}
                {item.message}
              </strong>
              <span>{new Date(item.created_at).toLocaleString()}</span>
            </div>
          </article>
        ))}
      </div>
      {inbox.error || read.error ? (
        <p role="alert">{(inbox.error ?? read.error)?.message}</p>
      ) : null}
      {!inbox.data?.items.length ? (
        <p className="page-state">暂无通知。</p>
      ) : null}
    </section>
  );
}
