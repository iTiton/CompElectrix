import { Component, type ErrorInfo, type ReactNode } from "react";

/** Si una página falla al pintarse, muestra un aviso con opción de recargar en lugar de dejar la pantalla vacía. */
export default class RedSeguridad extends Component<{ children: ReactNode; clave?: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Error en la interfaz:", error, info.componentStack);
  }

  componentDidUpdate(prev: { clave?: string }) {
    // Al cambiar de página, se vuelve a intentar
    if (prev.clave !== this.props.clave && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="tarjeta mx-auto mt-10 max-w-lg text-center">
        <h2 className="text-lg font-semibold">Algo ha fallado en esta pantalla</h2>
        <p className="mt-2 text-sm text-zinc-500">
          Tus datos están a salvo. Recarga la página; si vuelve a pasar, copia este mensaje para revisarlo:
        </p>
        <pre className="mt-3 overflow-x-auto rounded-xl bg-zinc-100 p-3 text-left text-xs dark:bg-zinc-800">{String(this.state.error.message)}</pre>
        <button className="btn-primario mt-4" onClick={() => location.reload()}>Recargar</button>
      </div>
    );
  }
}
