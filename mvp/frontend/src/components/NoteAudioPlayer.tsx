import { useRef, useState } from "react";

interface Props {
  audioUrl: string;
}

export function NoteAudioPlayer({ audioUrl }: Props) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);

  async function togglePlayback() {
    const audio = audioRef.current;
    if (!audio) return;

    if (playing) {
      audio.pause();
      setPlaying(false);
      return;
    }

    try {
      await audio.play();
      setPlaying(true);
    } catch {
      setPlaying(false);
    }
  }

  return (
    <div className="note-audio">
      <audio
        ref={audioRef}
        src={audioUrl}
        preload="none"
        onEnded={() => setPlaying(false)}
        onPause={() => setPlaying(false)}
      />
      <button
        className="audio-btn"
        type="button"
        onClick={togglePlayback}
        aria-label={playing ? "Pause note audio" : "Play note audio"}
      >
        {playing ? "Pause" : "Play"}
      </button>
    </div>
  );
}
