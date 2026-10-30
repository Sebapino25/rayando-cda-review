function ReproductorClip({ clip }) {
  // Sin video en YouTube (SPAreírse, por ahora): se reproduce el vertical.mp4 desde Supabase Storage.
  if (!clip.youtube_video_id && clip.video_url) {
    return (
      <div className="bg-black flex justify-center">
        <video
          className="h-[70vh] max-h-[640px] aspect-[9/16] bg-black"
          src={clip.video_url}
          poster={clip.portada_url || undefined}
          controls
          playsInline
          preload="metadata"
        />
      </div>
    )
  }
  // Publicado sin YouTube y con el mp4 ya borrado de Storage (limpiar_clips.py).
  if (!clip.youtube_video_id) {
    return (
      <div className="aspect-video bg-black flex items-center justify-center text-sm text-neutral-400">
        El video ya no está en la app (se borró tras publicarlo).
      </div>
    )
  }
  return (
    <div className="aspect-video bg-black">
      <iframe
        className="w-full h-full"
        src={`https://www.youtube.com/embed/${clip.youtube_video_id}`}
        title={clip.youtube_titulo || 'Clip'}
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
      />
    </div>
  )
}

export default ReproductorClip
