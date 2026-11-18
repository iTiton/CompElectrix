import { BarChart3, Clock, Home, LayoutGrid, Laptop, Menu, Moon, Settings, Sun, Tags, Zap } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import AvisoActualizacion from "./components/AvisoActualizacion";
import RedSeguridad from "./components/RedSeguridad";
import { useVersion } from "./components/ui";
import Ajustes from "./pages/Ajustes";
import DomicilioPage from "./pages/Domicilio";
import Inicio from "./pages/Inicio";
import Tarifas from "./pages/Tarifas";

// La comparativa lleva las gráficas (la parte más pesada): se carga solo al abrirla
const ComparativaPage = lazy(() => import("./pages/Comparativa"));
const Precios = lazy(() => import("./pages/Precios"));

/** Dirección de la portada de Wall-O si la aplicación se abrió a través del portal. */
function urlPortal(): string | null {
  const puerto = document.querySelector('meta[name="wallo-portal"]')?.getAttribute("content");
  return puerto ? `${location.protocol}//${location.hostname}:${puerto}/` : null;
}
const PORTAL = urlPortal();

type Tema = "claro" | "oscuro" | "sistema";

function useTema() {
  const [tema, setTema] = useState<Tema>(() => {
    try {
      return (localStorage.getItem("tema") as Tema) || "sistema";
    } catch {
      return "sistema";
    }
  });
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const aplicar = () =>
      document.documentElement.classList.toggle("dark", tema === "oscuro" || (tema === "sistema" && mq.matches));
    aplicar();
    try {
      localStorage.setItem("tema", tema);
    } catch {
      /* almacenamiento no disponible */
    }
    mq.addEventListener("change", aplicar);
    return () => mq.removeEventListener("change", aplicar);
  }, [tema]);
  return [tema, setTema] as const;
}

const NAV = [
  { a: "/", icono: Home, texto: "Domicilios" },
  { a: "/comparativa", icono: BarChart3, texto: "Comparativa" },
  { a: "/precios", icono: Clock, texto: "Precio PVPC" },
  { a: "/tarifas", icono: Tags, texto: "Tarifas" },
  { a: "/ajustes", icono: Settings, texto: "Ajustes" },
];

export default function App() {
  const [tema, setTema] = useTema();
  const version = useVersion();
  const [menu, setMenu] = useState(false);
  const loc = useLocation();
  useEffect(() => setMenu(false), [loc.pathname]);

  const temas: { v: Tema; i: typeof Sun; t: string }[] = [
    { v: "claro", i: Sun, t: "Claro" },
    { v: "oscuro", i: Moon, t: "Oscuro" },
    { v: "sistema", i: Laptop, t: "Sistema" },
  ];

  return (
    <div className="min-h-screen md:flex">
      <AvisoActualizacion />
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-4 py-3 md:hidden dark:border-zinc-800 dark:bg-zinc-900">
        <Logo />
        <div className="flex items-center gap-1">
          {PORTAL && (
            <a className="btn p-2" href={PORTAL} aria-label="Volver al portal" title="Volver al portal"><LayoutGrid size={20} /></a>
          )}
          <button className="btn p-2" onClick={() => setMenu(!menu)} aria-label="Menú"><Menu size={20} /></button>
        </div>
      </header>
      <aside
        className={`${menu ? "block" : "hidden"} border-r border-zinc-200 bg-white md:sticky md:top-0 md:flex md:h-screen md:w-60 md:flex-col dark:border-zinc-800 dark:bg-zinc-900`}
      >
        <div className="hidden px-5 py-5 md:block"><Logo /></div>
        <nav className="flex flex-col gap-1 px-3 py-2 md:flex-1">
          {NAV.map(({ a, icono: I, texto }) => (
            <NavLink
              key={a}
              to={a}
              end={a === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? "bg-acento-50 text-acento-700 dark:bg-acento-700/20 dark:text-acento-400"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                }`
              }
            >
              <I size={18} /> {texto}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-2 p-3">
          {PORTAL && (
            <a
              href={PORTAL}
              className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
            >
              <LayoutGrid size={18} /> Volver al portal
            </a>
          )}
          <div className="flex rounded-xl bg-zinc-100 p-1 dark:bg-zinc-800">
            {temas.map(({ v, i: I, t }) => (
              <button
                key={v}
                onClick={() => setTema(v)}
                title={t}
                aria-label={`Tema ${t}`}
                className={`flex flex-1 justify-center rounded-lg py-1.5 transition ${
                  tema === v ? "bg-white shadow-sm dark:bg-zinc-950" : "text-zinc-500"
                }`}
              >
                <I size={16} />
              </button>
            ))}
          </div>
          {version && <p className="px-1 text-center text-xs text-zinc-400 dark:text-zinc-500">CompElectrix {version}</p>}
        </div>
      </aside>
      <main className="mx-auto w-full max-w-6xl flex-1 p-4 md:p-8">
        <RedSeguridad clave={loc.pathname}>
        <Suspense fallback={<p className="text-sm text-zinc-500">Cargando…</p>}>
        <Routes>
          <Route path="/" element={<Inicio />} />
          <Route path="/domicilios/:id" element={<DomicilioPage />} />
          <Route path="/comparativa" element={<ComparativaPage />} />
          <Route path="/precios" element={<Precios />} />
          <Route path="/tarifas" element={<Tarifas />} />
          <Route path="/ajustes" element={<Ajustes />} />
        </Routes>
        </Suspense>
        </RedSeguridad>
      </main>
    </div>
  );
}

function Logo() {
  return (
    <div className="flex items-center gap-2 font-semibold">
      <span className="rounded-lg bg-acento-600 p-1.5 text-white"><Zap size={16} /></span>
      CompElectrix
    </div>
  );
}
