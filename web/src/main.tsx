import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  BookOpen,
  Check,
  ChefHat,
  ChevronRight,
  Clock3,
  CookingPot,
  Flame,
  LayoutGrid,
  Leaf,
  ListChecks,
  Minus,
  Plus,
  Search,
  Settings2,
  SlidersHorizontal,
  Utensils,
  X,
} from "lucide-react";
import "./style.css";

type Step = {
  id: string;
  instruction: string;
  duration_seconds?: number;
  mode?: string;
  resources?: Record<string, number>;
  depends_on: string[];
};
type Recipe = {
  id: string;
  title: string;
  original_title?: string;
  image_url?: string;
  category?: string;
  status: string;
  version: number;
  servings: number;
  servings_note?: string;
  notes?: string[];
  source: { name: string; url?: string; attribution: string };
  ingredients: { text: string; name?: string }[];
  steps: Step[];
  has_profile: boolean;
  profile_outdated: boolean;
};
type Task = {
  id: string;
  recipe_id: string;
  recipe_title: string;
  instruction: string;
  start: number;
  end: number;
  mode: string;
  resources: Record<string, number>;
  depends_on: string[];
};
type Plan = {
  id: string;
  tasks: Task[];
  recipes: Recipe[];
  duration_seconds: number;
  sequential_seconds: number;
  completed: string[];
};
type History = {
  id: string;
  titles: string[];
  created_at: string;
  duration_seconds: number;
  completed_count: number;
};
const resourceLabels: Record<string, string> = {
  person: "做饭的人",
  burner: "灶头",
  wok: "炒锅",
  pot: "汤锅",
  board: "砧板",
  oven: "烤箱",
};
const categories: Record<string, string> = {
  Vegetarian: "蔬食",
  Chicken: "鸡肉",
  Beef: "牛肉",
  Pork: "猪肉",
  Seafood: "海鲜",
  Side: "配菜",
  Starter: "前菜",
  Miscellaneous: "其他",
  Vegan: "纯素",
};
const minutes = (seconds: number) => Math.round((seconds / 60) * 10) / 10;
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(import.meta.env.BASE_URL + "api" + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const d = await r.json();
  if (!r.ok)
    throw new Error(typeof d.detail === "string" ? d.detail : "请检查输入内容");
  return d;
}

function App() {
  const [recipes, setRecipes] = useState<Recipe[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [view, setView] = useState("library"),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [selected, setSelected] = useState<string[]>([]);
  const [resources, setResources] = useState<Record<string, number>>(() => {
    try {
      return (
        JSON.parse(localStorage.getItem("cookflow-kitchen") || "null") || {
          person: 1,
          burner: 2,
          wok: 1,
          pot: 1,
          board: 1,
          oven: 0,
        }
      );
    } catch {
      return { person: 1, burner: 2, wok: 1, pot: 1, board: 1, oven: 0 };
    }
  });
  const [detail, setDetail] = useState<Recipe | null>(null),
    [review, setReview] = useState(false),
    [plan, setPlan] = useState<Plan | null>(null),
    [busy, setBusy] = useState(false),
    [history, setHistory] = useState<History[]>([]);
  useEffect(() => {
    localStorage.setItem("cookflow-kitchen", JSON.stringify(resources));
  }, [resources]);
  const refresh = () =>
    api<{ items: Recipe[] }>("/recipes").then((d) => setRecipes(d.items));
  useEffect(() => {
    refresh()
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    api<{ items: History[] }>("/plans")
      .then((d) => setHistory(d.items))
      .catch(() => {});
    const id = localStorage.getItem("cookflow-plan");
    if (id)
      api<Plan>("/plans/" + id)
        .then(setPlan)
        .catch(() => localStorage.removeItem("cookflow-plan"));
  }, []);
  const chosen = selected
      .map((id) => recipes.find((r) => r.id === id)!)
      .filter(Boolean),
    drafts = chosen.filter((r) => r.status !== "ready");
  const visible = recipes.filter(
    (r) =>
      (filter === "all" ||
        (filter === "ready" ? r.status === "ready" : r.category === filter)) &&
      `${r.title} ${r.original_title || ""} ${r.ingredients.map((i) => i.text).join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  function toggle(id: string) {
    setSelected((s) =>
      s.includes(id)
        ? s.filter((x) => x !== id)
        : s.length < 6
          ? [...s, id]
          : s,
    );
  }
  async function generate() {
    setError("");
    if (drafts.length) {
      setDetail(drafts[0]);
      setReview(true);
      return;
    }
    setBusy(true);
    try {
      const p = await api<Plan>("/plans", {
        method: "POST",
        body: JSON.stringify({ recipe_ids: selected, resources }),
      });
      setPlan(p);
      localStorage.setItem("cookflow-plan", p.id);
      setView("timeline");
      const h = await api<{ items: History[] }>("/plans");
      setHistory(h.items);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function complete(task: Task) {
    if (!plan) return;
    setBusy(true);
    try {
      const completed = plan.completed.includes(task.id)
        ? plan.completed.filter((id) => id !== task.id)
        : [...plan.completed, task.id];
      setPlan(
        await api<Plan>(`/plans/${plan.id}/progress`, {
          method: "PATCH",
          body: JSON.stringify({ completed }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView("library");
          }}
        >
          <span className="brand-icon">
            <CookingPot size={23} />
          </span>
          CookFlow<span className="brand-dot">.</span>
        </a>
        <p className="brand-sub">让下厨，从容一点。</p>
        <div className="nav-label">我的厨房</div>
        <nav>
          {[
            { id: "library", icon: BookOpen, label: "食谱收藏" },
            { id: "timeline", icon: ListChecks, label: "做饭时间线" },
            { id: "kitchen", icon: Settings2, label: "厨房配置" },
            { id: "history", icon: Clock3, label: "最近的安排" },
          ].map((n) => (
            <button
              key={n.id}
              className={view === n.id ? "nav-item active" : "nav-item"}
              onClick={() => setView(n.id)}
            >
              <n.icon size={19} />
              {n.label}
              {n.id === "library" && (
                <span className="nav-count">{recipes.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="leaf-badge">
            <Leaf size={20} />
          </span>
          <strong>一餐一饭，好好生活</strong>
          <p>
            从选菜到出锅，
            <br />
            把忙乱留给计划。
          </p>
          <div className="local-status">
            <i />
            本地厨房 · 初版
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>
            我的厨房 <ChevronRight size={14} />{" "}
            {
              (
                {
                  library: "食谱收藏",
                  timeline: "做饭时间线",
                  kitchen: "厨房配置",
                  history: "最近的安排",
                } as Record<string, string>
              )[view]
            }
          </span>
          <div className="top-meta">
            <span className="live-dot" />
            笔记本食谱库 <span className="avatar">我</span>
          </div>
        </header>
        {error && (
          <div className="error" role="alert">
            {error}
            <button aria-label="关闭错误" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        <main>
          {view === "library" && (
            <>
              <section className="hero">
                <div className="hero-copy">
                  <div className="eyebrow">
                    <span /> A LITTLE LESS RUSH, A LITTLE MORE JOY
                  </div>
                  <h1>今天，想好好吃什么？</h1>
                  <p>选几道喜欢的菜，把厨房交给有条理的计划。</p>
                  <div className="hero-meta">
                    <span>
                      <BookOpen size={15} /> {recipes.length} 道食谱
                    </span>
                    <span>
                      <ChefHat size={16} />{" "}
                      {recipes.filter((r) => r.status === "ready").length}{" "}
                      道已确认调度
                    </span>
                  </div>
                </div>
                <div className="hero-art" aria-hidden="true">
                  <div className="orbit orbit-one" />
                  <div className="orbit orbit-two" />
                  <div className="plate">
                    <div className="plate-inner">
                      <Leaf className="plate-leaf" size={70} />
                      <span className="tomato t1" />
                      <span className="tomato t2" />
                      <span className="tomato t3" />
                    </div>
                  </div>
                  <span className="art-label">
                    <Check size={13} /> 今晚，从容开饭
                  </span>
                </div>
              </section>
              <div className="content-grid">
                <section className="library">
                  <div className="section-heading">
                    <div>
                      <div className="eyebrow muted">THE RECIPE COLLECTION</div>
                      <h2>
                        你的灵感，从这里开始<span>{recipes.length}</span>
                      </h2>
                    </div>
                    <LayoutGrid size={18} />
                  </div>
                  <div className="search">
                    <Search size={18} />
                    <input
                      aria-label="搜索食谱"
                      placeholder="找一道菜，或一种食材…"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                    <span>搜索</span>
                  </div>
                  <div className="filters">
                    {[
                      ["all", "全部食谱"],
                      ["ready", "可调度"],
                      ...Array.from(
                        new Set(recipes.map((r) => r.category).filter(Boolean)),
                      ).map((c) => [c!, categories[c!] || c!]),
                    ].map(([id, label]) => (
                      <button
                        key={id}
                        onClick={() => setFilter(id)}
                        className={filter === id ? "chip selected" : "chip"}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {loading ? (
                    <div className="empty">正在打开你的食谱库…</div>
                  ) : !visible.length ? (
                    <div className="empty">
                      没有找到匹配的食谱，换一个关键词试试。
                    </div>
                  ) : (
                    <div className="recipe-grid">
                      {visible.map((r) => (
                        <article
                          className={
                            "recipe-card " +
                            (selected.includes(r.id) ? "is-selected" : "")
                          }
                          key={r.id}
                        >
                          <button
                            className="card-photo"
                            onClick={() => {
                              setDetail(r);
                              setReview(false);
                            }}
                            aria-label={"查看" + r.title}
                          >
                            {r.image_url ? (
                              <img
                                src={r.image_url + "/medium"}
                                alt={r.title}
                                loading="lazy"
                                onError={(e) => {
                                  e.currentTarget.style.display = "none";
                                }}
                              />
                            ) : (
                              <CookingPot size={56} />
                            )}
                            <span
                              className={
                                "status-badge " +
                                (r.status === "ready" ? "ready" : "")
                              }
                            >
                              {r.status === "ready" ? (
                                <Check size={11} />
                              ) : (
                                <SlidersHorizontal size={11} />
                              )}{" "}
                              {r.status === "ready" ? "可调度" : "待完善"}
                            </span>
                          </button>
                          <div className="card-body">
                            <div className="card-category">
                              {categories[r.category || ""] ||
                                r.category ||
                                "开发示例"}{" "}
                              <span>·</span> {r.source.name}
                            </div>
                            <button
                              className="card-title"
                              onClick={() => {
                                setDetail(r);
                                setReview(false);
                              }}
                            >
                              {r.title}
                            </button>
                            <p className="original-title">
                              {r.ingredients.slice(0, 3).map(i => i.name || i.text).join(" · ")}
                            </p>
                            <div className="card-bottom">
                              <span>
                                <Utensils size={13} /> {r.ingredients.length}{" "}
                                种食材 <span className="middot">·</span>{" "}
                                {r.steps.length} 步
                              </span>
                              <button
                                className={
                                  "add-button " +
                                  (selected.includes(r.id) ? "added" : "")
                                }
                                disabled={
                                  !selected.includes(r.id) &&
                                  selected.length >= 6
                                }
                                onClick={() => toggle(r.id)}
                                aria-label={
                                  (selected.includes(r.id) ? "移除" : "选择") +
                                  r.title
                                }
                              >
                                {selected.includes(r.id) ? (
                                  <Check size={17} />
                                ) : (
                                  <Plus size={17} />
                                )}
                              </button>
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                  <p className="source-note">
                    外部食谱与图片来源于 TheMealDB ·
                    中文菜名为展示译名，做法保留来源原文
                  </p>
                </section>
                <aside className="meal-panel">
                  <div className="meal-heading">
                    <span className="small-icon">
                      <CookingPot size={19} />
                    </span>
                    <div>
                      <h3>这顿吃什么</h3>
                      <p>把喜欢的菜，放进今天的菜单</p>
                    </div>
                  </div>
                  <div className="meal-count">
                    已选 {chosen.length} 道 <span>最多 6 道</span>
                  </div>
                  {chosen.length ? (
                    <div className="selected-list">
                      {chosen.map((r) => (
                        <div className="selected-item" key={r.id}>
                          <div className="mini-photo">
                            {r.image_url ? (
                              <img src={r.image_url + "/small"} alt="" />
                            ) : (
                              <Leaf size={20} />
                            )}
                          </div>
                          <button
                            onClick={() => {
                              setDetail(r);
                              setReview(r.status !== "ready");
                            }}
                          >
                            <strong>{r.title}</strong>
                            <small>
                              {r.status === "ready"
                                ? "调度信息已确认"
                                : "点此补全调度信息"}
                            </small>
                          </button>
                          <button
                            className="remove"
                            aria-label={"移除" + r.title}
                            onClick={() => toggle(r.id)}
                          >
                            <X size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="menu-empty">
                      <div>
                        <Utensils size={28} />
                      </div>
                      <p>一顿好饭，从一道菜开始</p>
                      <small>点击食谱右下角的 + 添加</small>
                    </div>
                  )}
                  <div className="kitchen-summary">
                    <div>
                      <strong>厨房准备好了</strong>
                      <button onClick={() => setView("kitchen")}>
                        调整 <ChevronRight size={12} />
                      </button>
                    </div>
                    <p>
                      <ChefHat size={14} />
                      {resources.person} 人做饭 <span>·</span>
                      <Flame size={14} />
                      {resources.burner} 个灶头
                    </p>
                  </div>
                  <button
                    className="primary generate"
                    disabled={!chosen.length || busy}
                    onClick={generate}
                  >
                    {busy
                      ? "正在安排…"
                      : drafts.length
                        ? "确认食谱，开始安排"
                        : "生成做饭时间线"}
                    <ArrowRight size={17} />
                  </button>
                  <p className="panel-note">
                    {drafts.length
                      ? `${drafts.length} 道菜还需要确认耗时和厨具`
                      : "把准备工作排好，享受做饭的过程。"}
                  </p>
                  <div className="little-tip">
                    <Leaf size={17} />
                    <p>
                      先选一道主菜，再搭配蔬菜和汤。
                      <br />
                      一顿饭，不必太复杂。
                    </p>
                  </div>
                </aside>
              </div>
            </>
          )}
          {view === "kitchen" && (
            <section className="page-section">
              <div className="eyebrow muted">YOUR KITCHEN</div>
              <h1>先认识一下，你的厨房。</h1>
              <p className="intro">告诉我们有哪些帮手，安排才不会手忙脚乱。</p>
              <div className="resource-grid">
                {Object.entries(resourceLabels).map(([key, label]) => (
                  <div className="resource-card" key={key}>
                    <span className="small-icon">
                      {key === "person" ? (
                        <ChefHat />
                      ) : key === "burner" ? (
                        <Flame />
                      ) : (
                        <CookingPot />
                      )}
                    </span>
                    <h3>{label}</h3>
                    <div className="counter">
                      <button
                        aria-label={"减少" + label}
                        disabled={resources[key] <= (key === "person" ? 1 : 0)}
                        onClick={() =>
                          setResources({
                            ...resources,
                            [key]: resources[key] - 1,
                          })
                        }
                      >
                        <Minus size={16} />
                      </button>
                      <strong>{resources[key]}</strong>
                      <button
                        aria-label={"增加" + label}
                        disabled={resources[key] >= 8}
                        onClick={() =>
                          setResources({
                            ...resources,
                            [key]: resources[key] + 1,
                          })
                        }
                      >
                        <Plus size={16} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <button className="primary" onClick={() => setView("library")}>
                配置好了，去选菜 <ArrowRight size={16} />
              </button>
            </section>
          )}
          {view === "timeline" && (
            <section className="page-section">
              <div className="eyebrow muted">ONE STEP AT A TIME</div>
              <h1>有条不紊地，做好一顿饭。</h1>
              {!plan ? (
                <div className="empty large">
                  <Clock3 size={42} />
                  <h3>还没有做饭安排</h3>
                  <p>先选择食谱、确认步骤，再生成你的时间线。</p>
                  <button
                    className="primary"
                    onClick={() => setView("library")}
                  >
                    去选几道菜 <ArrowRight size={16} />
                  </button>
                </div>
              ) : (
                <>
                  <div className="plan-summary">
                    <div>
                      <small>预计用时</small>
                      <strong>
                        {minutes(plan.duration_seconds)} <em>分钟</em>
                      </strong>
                    </div>
                    <div>
                      <small>这顿菜单</small>
                      <strong>
                        {plan.recipes.length} <em>道菜</em>
                      </strong>
                    </div>
                    <div>
                      <small>已完成</small>
                      <strong>
                        {plan.completed.length}{" "}
                        <em>/ {plan.tasks.length} 步</em>
                      </strong>
                    </div>
                  </div>
                  <p className="intro">
                    {plan.recipes.map((r) => r.title).join(" · ")}
                    <br />
                    <small>
                      时间从开始做饭起算，采用你确认的耗时估计。勾选步骤会保存进度。
                    </small>
                  </p>
                  <div className="timeline">
                    {plan.tasks.map((t) => (
                      <div
                        key={t.id}
                        className={
                          "timeline-row " +
                          (plan.completed.includes(t.id) ? "done" : "")
                        }
                      >
                        <div className="time">
                          {minutes(t.start)}
                          <small>分钟</small>
                        </div>
                        <button
                          disabled={busy}
                          className="task-check"
                          onClick={() => complete(t)}
                          aria-label={"完成步骤 " + t.recipe_title + " " + t.id}
                        >
                          {plan.completed.includes(t.id) && <Check size={15} />}
                        </button>
                        <div className="task-card">
                          <div>
                            <span className="dish-tag">{t.recipe_title}</span>
                            <span className="task-time">
                              <Clock3 size={13} />
                              {minutes(t.end - t.start)} 分钟 ·{" "}
                              {t.mode === "passive"
                                ? "等待，可处理其他事"
                                : "需要动手"}
                            </span>
                          </div>
                          <p>{t.instruction}</p>
                          <small>
                            {Object.entries(t.resources)
                              .map(
                                ([key, n]) =>
                                  `${resourceLabels[key] || key} ×${n}`,
                              )
                              .join(" · ")}
                          </small>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </section>
          )}
          {view === "history" && (
            <section className="page-section">
              <div className="eyebrow muted">RECENT MEALS</div>
              <h1>每一顿饭，都有迹可循。</h1>
              {!history.length ? (
                <div className="empty">生成第一份时间线后，会保存在这里。</div>
              ) : (
                <div className="history-list">
                  {history.map((h) => (
                    <button
                      key={h.id}
                      onClick={async () => {
                        try {
                          setPlan(await api<Plan>("/plans/" + h.id));
                          localStorage.setItem("cookflow-plan", h.id);
                          setView("timeline");
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    >
                      <span className="small-icon">
                        <CookingPot />
                      </span>
                      <div>
                        <strong>{h.titles.join("、")}</strong>
                        <small>
                          {new Date(h.created_at).toLocaleString("zh-CN")} ·{" "}
                          {minutes(h.duration_seconds)} 分钟
                        </small>
                      </div>
                      <ChevronRight size={18} />
                    </button>
                  ))}
                </div>
              )}
            </section>
          )}
        </main>
        <footer>
          CookFlow <span>从容做饭，好好生活。</span>
          <span>LOCAL-FIRST KITCHEN</span>
        </footer>
      </div>
      {detail && (
        <RecipeModal
          recipe={detail}
          initialReview={review}
          onClose={() => setDetail(null)}
          onSave={async () => {
            await refresh();
            setDetail(null);
          }}
        />
      )}
    </div>
  );
}

function RecipeModal({
  recipe,
  initialReview,
  onClose,
  onSave,
}: {
  recipe: Recipe;
  initialReview: boolean;
  onClose: () => void;
  onSave: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(initialReview),
    [steps, setSteps] = useState<Step[]>(
      recipe.steps.map((s) => ({
        ...s,
        resources: { ...s.resources },
        mode: s.mode || "active",
      })),
    ),
    [servings, setServings] = useState(recipe.servings),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", close);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", close);
      document.body.style.overflow = prev;
    };
  }, []);
  function update(i: number, patch: Partial<Step>) {
    setSteps((s) => s.map((v, j) => (j === i ? { ...v, ...patch } : v)));
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const ordered: Step[] = steps.map((s, i) => ({
        ...s,
        id: `s${i + 1}`,
        depends_on: i ? [`s${i}`] : [],
        resources: {
          ...s.resources,
          ...(s.mode === "active" ? { person: 1 } : {}),
        },
      }));
      const holds = [];
      for (const resource of ["wok", "pot"]) {
        const used = ordered.filter((s) => s.resources?.[resource]);
        if (used.length > 1)
          holds.push({
            resource,
            quantity: 1,
            from_step: used[0].id,
            through_step: used[used.length - 1].id,
          });
      }
      await api("/profiles/" + recipe.id, {
        method: "POST",
        body: JSON.stringify({
          base_version: recipe.version,
          servings,
          steps: ordered,
          resource_holds: holds,
        }),
      });
      await onSave();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={recipe.title}
      >
        <button className="modal-close" onClick={onClose} aria-label="关闭详情">
          <X />
        </button>
        <div className="modal-top">
          <div className="eyebrow muted">
            {recipe.source.name} · VERSION {recipe.version}
          </div>
          <h2>{recipe.title}</h2>
          <p>{recipe.ingredients.length} 种食材 · {recipe.steps.length} 个步骤</p>
          <div className="modal-tabs">
            <button
              className={!editing ? "active" : ""}
              onClick={() => setEditing(false)}
            >
              食材与做法
            </button>
            <button
              className={editing ? "active" : ""}
              onClick={() => setEditing(true)}
            >
              调度信息
            </button>
          </div>
        </div>
        <div className="modal-content">
          {error && (
            <div role="alert" className="error">
              {error}
            </div>
          )}
          {!editing ? (
            <>
              <div className="ingredients">
                <h3>准备这些食材</h3>
                {recipe.ingredients.map((x, i) => (
                  <div key={i}>
                    <span />
                    {x.text}
                  </div>
                ))}
              </div>
              {recipe.notes?.length ? (
                <div className="recipe-notes">
                  <h3>来源提示</h3>
                  {recipe.notes.map((note, i) => (
                    <p className="muted-text" key={i}>
                      {note}
                    </p>
                  ))}
                </div>
              ) : null}
              <h3>原始做法</h3>
              <p className="muted-text">保留来源英文。中文菜名是展示译名。</p>
              {recipe.steps.map((s, i) => (
                <div className="instruction" key={s.id}>
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  <p>{s.instruction}</p>
                </div>
              ))}
              <a
                className="source-link"
                href={recipe.source.url || "#"}
                target="_blank"
                rel="noreferrer"
              >
                查看来源 · {recipe.source.name} ↗
              </a>
              <p className="muted-text">{recipe.source.attribution}</p>
            </>
          ) : (
            <>
              <div className="review-notice">
                <SlidersHorizontal size={20} />
                <p>
                  把做法变成可执行的步骤。填写每步耗时、选择厨具；复合步骤可以拆开。顺序按下方列表执行。
                </p>
              </div>
              <label className="servings">
                这份食谱可供{" "}
                <input
                  type="number"
                  min="1"
                  max="30"
                  value={servings}
                  onChange={(e) => setServings(+e.target.value)}
                />{" "}
                人享用
              </label>
              {!recipe.has_profile && (
                <p className="muted-text">
                  来源没有逐步耗时和份数，请根据你的做法确认；这里的填写值按估计记录。
                </p>
              )}
              {steps.map((s, i) => (
                <div className="step-editor" key={i}>
                  <div className="step-editor-title">
                    <strong>步骤 {String(i + 1).padStart(2, "0")}</strong>
                    <button
                      disabled={steps.length === 1}
                      onClick={() => setSteps(steps.filter((_, j) => j !== i))}
                    >
                      删除
                    </button>
                  </div>
                  <textarea
                    aria-label={`步骤 ${i + 1} 做法`}
                    value={s.instruction}
                    onChange={(e) => update(i, { instruction: e.target.value })}
                  />
                  <div className="step-settings">
                    <label>
                      预计耗时{" "}
                      <input
                        aria-label={`步骤 ${i + 1} 分钟`}
                        type="number"
                        min="0.1"
                        max="1440"
                        step="0.1"
                        placeholder="分钟"
                        value={
                          s.duration_seconds ? minutes(s.duration_seconds) : ""
                        }
                        onChange={(e) =>
                          update(i, {
                            duration_seconds: Math.round(+e.target.value * 60),
                          })
                        }
                      />{" "}
                      分钟
                    </label>
                    <select
                      aria-label={`步骤 ${i + 1} 模式`}
                      value={s.mode}
                      onChange={(e) => {
                        const res = { ...s.resources };
                        delete res.person;
                        update(i, { mode: e.target.value, resources: res });
                      }}
                    >
                      <option value="active">需要动手</option>
                      <option value="passive">被动等待</option>
                    </select>
                  </div>
                  <div className="step-resources">
                    {Object.entries(resourceLabels)
                      .filter(([k]) => k !== "person")
                      .map(([key, label]) => (
                        <button
                          key={key}
                          className={
                            s.resources?.[key] ? "chip selected" : "chip"
                          }
                          onClick={() => {
                            const res = { ...s.resources };
                            if (res[key]) delete res[key];
                            else res[key] = 1;
                            update(i, { resources: res });
                          }}
                        >
                          {s.resources?.[key] && <Check size={11} />} {label}
                        </button>
                      ))}
                  </div>
                </div>
              ))}
              <button
                className="secondary"
                onClick={() =>
                  setSteps([
                    ...steps,
                    {
                      id: `new${steps.length}`,
                      instruction: "",
                      mode: "active",
                      resources: {},
                      depends_on: [],
                    },
                  ])
                }
              >
                <Plus size={15} />
                添加步骤
              </button>
              <p className="muted-text">
                同一道菜的炒锅和汤锅，从首次使用到最后一次使用持续保留；等待时仍在加热，请同时选中灶头。
              </p>
            </>
          )}
        </div>
        <div className="modal-footer">
          <button className="secondary" onClick={onClose}>
            返回食谱库
          </button>
          {editing ? (
            <button className="primary" disabled={busy} onClick={save}>
              {busy ? "保存中…" : "确认并保存调度信息"}
              <Check size={16} />
            </button>
          ) : (
            <button className="primary" onClick={() => setEditing(true)}>
              完善调度信息
              <ArrowRight size={16} />
            </button>
          )}
        </div>
      </section>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
