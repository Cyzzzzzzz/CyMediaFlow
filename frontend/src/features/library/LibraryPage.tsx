import { ArrowClockwise, CaretDown, MagnifyingGlass } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { MediaItem } from "../../api/types";
import { libraryApi, type LibrarySort } from "./api";
import { PosterCard } from "./PosterCard";
import { ScrapeDrawer } from "./ScrapeDrawer";

export function LibraryPage() {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<LibrarySort>("added_desc");
  const [selected, setSelected] = useState<MediaItem | null>(null);
  const [autoOpened, setAutoOpened] = useState(false);
  const library = useQuery({
    queryKey: ["library", search, sort],
    queryFn: () => libraryApi.list(search, sort),
  });

  useEffect(() => {
    const shouldOpenFirst = new URLSearchParams(window.location.search).get("open") === "first";
    if (shouldOpenFirst && library.data?.[0] && !autoOpened) {
      setSelected(library.data[0]);
      setAutoOpened(true);
    }
  }, [autoOpened, library.data]);
  return <div className="library-page">
    <header className="page-header"><div><h1>番剧库</h1></div><div className="header-actions">
      <label className="library-search"><MagnifyingGlass size={18} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索番剧" aria-label="搜索番剧" /></label>
      <label className="library-sort">
        <select value={sort} onChange={(event) => setSort(event.target.value as LibrarySort)} aria-label="排序方式">
          <option value="added_desc">最近添加</option>
          <option value="name_asc">按名称</option>
        </select>
        <CaretDown size={14} aria-hidden="true" />
      </label>
      <button className="icon-button" type="button" onClick={() => void library.refetch()} aria-label="刷新媒体库"><ArrowClockwise size={20} /></button>
    </div></header>
    <div className="library-meta"><span>{library.data?.length ?? 0} 部作品</span><span>点击海报配置刮削信息</span></div>
    {library.isError ? <div className="page-state">无法读取媒体目录，请检查设置。</div> : null}
    {library.isLoading ? <div className="poster-grid" aria-label="正在加载">{Array.from({ length: 10 }, (_, i) => <div className="poster-skeleton" key={i} />)}</div> : null}
    {library.data?.length === 0 ? <div className="page-state">没有找到匹配的番剧。</div> : null}
    {library.data?.length ? <div className="poster-grid">{library.data.map((item) => <PosterCard item={item} selected={selected?.id === item.id} key={item.id} onOpen={setSelected} />)}</div> : null}
    {selected ? <ScrapeDrawer item={selected} onClose={() => setSelected(null)} /> : null}
  </div>;
}
