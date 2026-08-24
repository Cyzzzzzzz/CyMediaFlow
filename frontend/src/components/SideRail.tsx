import { FilmSlate, House, SlidersHorizontal } from "@phosphor-icons/react";
import { NavLink } from "react-router-dom";

export function SideRail() {
  return <aside className="side-rail" aria-label="主导航">
    <NavLink className="brand-mark" to="/" aria-label="CyMediaFlow 首页"><FilmSlate size={23} weight="fill" /></NavLink>
    <nav>
      <NavLink className="rail-link" to="/" end aria-label="首页"><House size={23} weight="duotone" /><span>首页</span></NavLink>
      <NavLink className="rail-link" to="/settings" aria-label="设置"><SlidersHorizontal size={23} weight="duotone" /><span>设置</span></NavLink>
    </nav>
  </aside>;
}
