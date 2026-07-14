import { useState } from 'react'

export default function ReviewerGate({ onSubmit }) {
  const [name, setName] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    onSubmit(trimmed)
  }

  return (
    <div className="min-h-dvh flex items-center justify-center bg-primary px-5 py-safe pb-safe">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-surface rounded-3xl shadow-xl p-6 sm:p-8"
      >
        <div className="flex flex-col items-center text-center mb-6">
          <img
            src={`${import.meta.env.BASE_URL}logo.png`}
            alt="Rayando el CDA"
            className="w-16 h-16 rounded-2xl object-cover mb-4"
          />
          <h1 className="text-xl font-bold text-foreground">Rayando el CDA</h1>
          <p className="text-sm text-muted-foreground mt-1">Cola de revisión de clips</p>
        </div>

        <label htmlFor="reviewer-name" className="block text-sm font-semibold text-foreground mb-2">
          ¿Quién va a revisar hoy?
        </label>
        <input
          id="reviewer-name"
          type="text"
          autoFocus
          autoComplete="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Tu nombre"
          className="w-full h-14 px-4 rounded-xl border border-border bg-background text-base text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <p className="text-xs text-muted-foreground mt-2">
          Lo guardamos en este dispositivo para no volver a pedirlo.
        </p>

        <button
          type="submit"
          disabled={!name.trim()}
          className="mt-5 w-full h-14 rounded-xl bg-primary text-primary-foreground font-semibold text-base disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
        >
          Continuar
        </button>
      </form>
    </div>
  )
}
