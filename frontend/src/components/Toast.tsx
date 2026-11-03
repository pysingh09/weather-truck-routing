import { useEffect } from 'react'

export default function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 8000)
    return () => clearTimeout(t)
  }, [message, onClose])
  return (
    <div role="alert" className="pointer-events-auto flex max-w-md items-start gap-3 rounded-lg bg-red-600 px-4 py-3 text-sm text-white shadow-lg">
      <span className="flex-1">{message}</span>
      <button onClick={onClose} aria-label="Dismiss" className="text-white/80 hover:text-white">×</button>
    </div>
  )
}
