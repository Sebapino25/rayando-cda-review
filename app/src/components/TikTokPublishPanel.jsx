import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { SpinnerGap, ArrowsClockwise, Info, TiktokLogo } from '@phosphor-icons/react'
import { supabase } from '../lib/supabaseClient'

const MUSIC_URL = 'https://www.tiktok.com/legal/page/global/music-usage-confirmation/en'
const BRANDED_URL = 'https://www.tiktok.com/legal/page/global/bc-policy/en'
const CAPTION_MAX = 2200

// Etiquetas de privacidad de TikTok. Las opciones reales llegan de creator_info
// (dependen de si la cuenta es pública o privada) — acá solo se traducen.
const PRIVACY_LABELS = {
  PUBLIC_TO_EVERYONE: 'Todos',
  MUTUAL_FOLLOW_FRIENDS: 'Amigos (seguidores mutuos)',
  FOLLOWER_OF_CREATOR: 'Seguidores',
  SELF_ONLY: 'Solo yo (privado)',
}

function Switch({ checked, onChange, disabled, label, hint }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <span className={`text-sm font-medium ${disabled ? 'text-muted-foreground' : 'text-foreground'}`}>{label}</span>
        {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`shrink-0 mt-0.5 w-11 h-6 rounded-full transition-colors relative disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer ${
          checked ? 'bg-accent' : 'bg-border'
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
            checked ? 'translate-x-5' : ''
          }`}
        />
      </button>
    </div>
  )
}

/**
 * Pantalla de configuración de la publicación a TikTok (Content Posting API,
 * Direct Post). Las Content Sharing Guidelines de TikTok exigen que la persona
 * elija a mano, antes de publicar: la privacidad (sin valor por defecto), los
 * permisos de interacción, y la divulgación de contenido comercial, con el
 * texto de cumplimiento visible. Este panel junta esas elecciones y las emite
 * por onChange; publicar-clip/tiktok.ts las valida de nuevo server-side.
 */
export default function TikTokPublishPanel({ clip, onChange, onValidityChange }) {
  const [enabled, setEnabled] = useState(true)
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState('')
  const [info, setInfo] = useState(null) // { habilitado, auditoria_aprobada, data }
  const fetchedRef = useRef(false)

  const [privacy, setPrivacy] = useState('')
  const [allowComment, setAllowComment] = useState(false)
  const [allowDuet, setAllowDuet] = useState(false)
  const [allowStitch, setAllowStitch] = useState(false)
  const [disclose, setDisclose] = useState(false)
  const [yourBrand, setYourBrand] = useState(false)
  const [brandedContent, setBrandedContent] = useState(false)
  const [caption, setCaption] = useState(clip.copy_tiktok ?? '')

  const cargarInfo = useCallback(async () => {
    setLoading(true)
    setFetchError('')
    try {
      const { data, error } = await supabase.functions.invoke('publicar-clip', {
        body: { action: 'tiktok_creator_info' },
      })
      if (error) throw error
      if (data?.ok === false) throw new Error(data.error || 'No se pudo consultar TikTok.')
      setInfo(data)
    } catch (err) {
      setFetchError(err?.message || 'No se pudo consultar TikTok. Reintentá.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (enabled && !fetchedRef.current) {
      fetchedRef.current = true
      cargarInfo()
    }
  }, [enabled, cargarInfo])

  const data = info?.data
  const habilitado = info ? info.habilitado !== false : true
  const brandedNoPrivate = disclose && brandedContent
  const privacyOptions = useMemo(
    () => (data?.privacy_level_options ?? []).filter((o) => !(brandedNoPrivate && o === 'SELF_ONLY')),
    [data, brandedNoPrivate],
  )

  // Si la opción elegida deja de ser válida (p.ej. se marcó "contenido de marca"
  // y estaba en "Solo yo"), se limpia para forzar re-elección.
  useEffect(() => {
    if (privacy && !privacyOptions.includes(privacy)) setPrivacy('')
  }, [privacy, privacyOptions])

  // Respetar lo que la cuenta deshabilitó (creator_info manda).
  useEffect(() => {
    if (data?.comment_disabled && allowComment) setAllowComment(false)
    if (data?.duet_disabled && allowDuet) setAllowDuet(false)
    if (data?.stitch_disabled && allowStitch) setAllowStitch(false)
  }, [data, allowComment, allowDuet, allowStitch])

  const captionTrimmed = caption.trim()
  const tiktokActivo = enabled && habilitado && !!data
  const valid = !enabled || !habilitado
    ? true
    : loading || fetchError || !data
      ? false
      : privacy !== '' &&
        (!disclose || yourBrand || brandedContent) &&
        caption.length <= CAPTION_MAX &&
        captionTrimmed.length > 0
  const payload = tiktokActivo && valid
    ? {
        privacy_level: privacy,
        disable_comment: !allowComment,
        disable_duet: !allowDuet,
        disable_stitch: !allowStitch,
        brand_content_toggle: disclose && brandedContent,
        brand_organic_toggle: disclose && yourBrand,
        caption: captionTrimmed,
      }
    : null

  const payloadKey = JSON.stringify(payload)
  useEffect(() => {
    onChange(payload)
    onValidityChange(valid)
    // onChange/onValidityChange son setters de useState (estables); depende del
    // contenido serializado del payload para no disparar en cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payloadKey, valid])

  const complianceText = brandedContent ? (
    <>
      Al publicar, aceptás la{' '}
      <a href={BRANDED_URL} target="_blank" rel="noreferrer" className="underline font-medium">
        Política de Contenido de Marca
      </a>{' '}
      y la{' '}
      <a href={MUSIC_URL} target="_blank" rel="noreferrer" className="underline font-medium">
        Confirmación de uso de música
      </a>{' '}
      de TikTok.
    </>
  ) : (
    <>
      Al publicar, aceptás la{' '}
      <a href={MUSIC_URL} target="_blank" rel="noreferrer" className="underline font-medium">
        Confirmación de uso de música
      </a>{' '}
      de TikTok.
    </>
  )

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-3.5 py-3 bg-muted">
        <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <TiktokLogo size={18} weight="fill" />
          Publicar también en TikTok
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Publicar también en TikTok"
          onClick={() => setEnabled((v) => !v)}
          className={`shrink-0 w-11 h-6 rounded-full transition-colors relative cursor-pointer ${
            enabled ? 'bg-accent' : 'bg-border'
          }`}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
              enabled ? 'translate-x-5' : ''
            }`}
          />
        </button>
      </div>

      {enabled && (
        <div className="p-3.5 flex flex-col gap-3.5">
          {loading && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <SpinnerGap size={16} className="animate-spin" /> Cargando datos de la cuenta de TikTok…
            </p>
          )}

          {!loading && fetchError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 flex flex-col gap-2">
              <p className="text-sm text-destructive">{fetchError}</p>
              <p className="text-xs text-muted-foreground">
                Podés desactivar “Publicar también en TikTok” para publicar solo en YouTube e Instagram.
              </p>
              <button
                type="button"
                onClick={cargarInfo}
                className="self-start flex items-center gap-1.5 text-sm font-semibold text-primary cursor-pointer"
              >
                <ArrowsClockwise size={15} weight="bold" /> Reintentar
              </button>
            </div>
          )}

          {!loading && !fetchError && info && !habilitado && (
            <p className="flex items-start gap-1.5 text-sm text-warning bg-warning-bg/60 rounded-lg px-3 py-2">
              <Info size={16} className="shrink-0 mt-0.5" />
              La publicación automática a TikTok está desactivada (secret <code>PUBLICAR_TIKTOK</code>). El clip se
              publicará solo en YouTube e Instagram.
            </p>
          )}

          {!loading && !fetchError && data && (
            <>
              <div className="flex items-center gap-2.5">
                {data.creator_avatar_url ? (
                  <img
                    src={data.creator_avatar_url}
                    alt=""
                    className="w-9 h-9 rounded-full object-cover border border-border"
                  />
                ) : (
                  <div className="w-9 h-9 rounded-full bg-muted border border-border" />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground truncate">
                    {data.creator_nickname || 'Cuenta de TikTok'}
                  </p>
                  {data.creator_username && (
                    <p className="text-xs text-muted-foreground truncate">@{data.creator_username}</p>
                  )}
                </div>
              </div>

              <label className="block">
                <span className="block text-sm font-semibold text-foreground mb-1.5">Descripción (caption)</span>
                <textarea
                  rows={3}
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  className="w-full px-3.5 py-3 rounded-xl border border-border bg-background text-[15px] leading-snug text-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
                />
                <span
                  className={`block text-xs mt-1 text-right ${
                    caption.length > CAPTION_MAX ? 'text-destructive font-medium' : 'text-muted-foreground'
                  }`}
                >
                  {caption.length}/{CAPTION_MAX}
                </span>
              </label>

              <label className="block">
                <span className="block text-sm font-semibold text-foreground mb-1.5">¿Quién puede ver este video?</span>
                <select
                  value={privacy}
                  onChange={(e) => setPrivacy(e.target.value)}
                  className="w-full h-12 px-3 rounded-xl border border-border bg-background text-[15px] text-foreground focus:outline-none focus:ring-2 focus:ring-ring cursor-pointer"
                >
                  <option value="" disabled>
                    Elegí una opción
                  </option>
                  {privacyOptions.map((o) => (
                    <option key={o} value={o}>
                      {PRIVACY_LABELS[o] || o}
                    </option>
                  ))}
                </select>
                {brandedNoPrivate && (
                  <p className="text-xs text-muted-foreground mt-1">
                    El contenido de marca no puede ser privado (“Solo yo” queda deshabilitado).
                  </p>
                )}
              </label>

              <div className="rounded-xl border border-border px-3.5 py-2">
                <p className="text-sm font-semibold text-foreground mb-1">Permisos de interacción</p>
                <Switch
                  label="Permitir comentarios"
                  checked={allowComment}
                  disabled={Boolean(data.comment_disabled)}
                  hint={data.comment_disabled ? 'Deshabilitado en la configuración de la cuenta' : undefined}
                  onChange={setAllowComment}
                />
                <Switch
                  label="Permitir Dúo"
                  checked={allowDuet}
                  disabled={Boolean(data.duet_disabled)}
                  hint={data.duet_disabled ? 'Deshabilitado en la configuración de la cuenta' : undefined}
                  onChange={setAllowDuet}
                />
                <Switch
                  label="Permitir Stitch"
                  checked={allowStitch}
                  disabled={Boolean(data.stitch_disabled)}
                  hint={data.stitch_disabled ? 'Deshabilitado en la configuración de la cuenta' : undefined}
                  onChange={setAllowStitch}
                />
              </div>

              <div className="rounded-xl border border-border px-3.5 py-2">
                <Switch
                  label="Divulgar contenido comercial"
                  hint="Activalo si el video promociona una marca, producto o servicio."
                  checked={disclose}
                  onChange={(v) => {
                    setDisclose(v)
                    if (!v) {
                      setYourBrand(false)
                      setBrandedContent(false)
                    }
                  }}
                />
                {disclose && (
                  <div className="flex flex-col gap-2 pt-1.5 pb-1">
                    <label className="flex items-start gap-2 text-sm text-foreground cursor-pointer">
                      <input
                        type="checkbox"
                        checked={yourBrand}
                        onChange={(e) => setYourBrand(e.target.checked)}
                        className="mt-0.5 w-4 h-4 accent-accent"
                      />
                      <span>
                        <span className="font-medium">Tu propia marca</span> — promocionás tu marca, producto o servicio.
                      </span>
                    </label>
                    <label className="flex items-start gap-2 text-sm text-foreground cursor-pointer">
                      <input
                        type="checkbox"
                        checked={brandedContent}
                        onChange={(e) => setBrandedContent(e.target.checked)}
                        className="mt-0.5 w-4 h-4 accent-accent"
                      />
                      <span>
                        <span className="font-medium">Contenido de marca</span> — colaboración paga con otra marca.
                      </span>
                    </label>
                    {!yourBrand && !brandedContent && (
                      <p className="text-xs text-destructive font-medium">Elegí al menos una opción.</p>
                    )}
                  </div>
                )}
              </div>

              <p className="text-xs text-muted-foreground leading-relaxed">{complianceText}</p>
            </>
          )}
        </div>
      )}
    </div>
  )
}
