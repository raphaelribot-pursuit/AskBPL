import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../../auth/useAuth'
import { useAskChat } from '../../conversation/useAskChat'
import { AvatarTrigger } from './AvatarTrigger'
import { Modal } from './Modal'
import { PilotTranscript } from './PilotTranscript'
import { InputField } from './InputField'

/**
 * Wireframe v3 chat shell — the default post-login surface.
 *
 * Closed: 56px book FAB anchored bottom-right (`<AvatarTrigger />`).
 * Open  : 380px modal anchored 92px above the FAB (`<Modal />`), with the
 *         pilot transcript renderer and an auto-grow input field.
 *
 * Conversation state survives close/reopen because `useAskChat` lives at
 * the shell level (Wireframe §4 transcript persistence). Sign-out does the
 * full reset.
 *
 * The legacy draggable Spline avatar lives in `AvatarShellLegacy.tsx` and
 * is gated behind `VITE_ENABLE_AVATAR_SHELL`; the dispatcher in
 * `AskPilotShell.tsx` decides which one mounts.
 */

const SAMPLE_PROMPT =
  'Summarize gift acceptance prerequisites and who must approve unusually large pledges.'
const FIRST_OPEN_KEY = 'askbpl-pilot.greeted'
const NEAR_BOTTOM_PX = 60

type WireframeShellProps = {
  apiBase: string
  docsBase: string
}

export function WireframeShell({ apiBase, docsBase }: WireframeShellProps) {
  const navigate = useNavigate()
  const { session, signOut } = useAuth()
  const token = session?.token ?? null

  const [open, setOpen] = useState(false)
  const [composer, setComposer] = useState('')
  const [showSampleChip, setShowSampleChip] = useState(true)
  const [showFirstOpenHint, setShowFirstOpenHint] = useState(false)
  const [showJumpDown, setShowJumpDown] = useState(false)

  const fabRef = useRef<HTMLButtonElement | null>(null)
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const isNearBottomRef = useRef(true)

  const handleSessionExpired = useCallback(() => {
    signOut()
    setOpen(false)
    navigate('/login', { replace: true })
  }, [navigate, signOut])

  const handleRestoreInput = useCallback(
    (text: string) => {
      // Only restore if the tester hasn’t already started typing again.
      setComposer((current) => (current ? current : text))
    },
    [],
  )

  const chat = useAskChat({
    apiBase,
    docsBase,
    token,
    onSessionExpired: handleSessionExpired,
    onRestoreInput: handleRestoreInput,
  })

  const handleOpen = useCallback(() => {
    setOpen(true)
    if (typeof window !== 'undefined') {
      try {
        const greeted = window.sessionStorage.getItem(FIRST_OPEN_KEY) === '1'
        setShowFirstOpenHint(!greeted)
        window.sessionStorage.setItem(FIRST_OPEN_KEY, '1')
      } catch {
        setShowFirstOpenHint(true)
      }
    }
  }, [])

  const handleClose = useCallback(() => {
    setOpen(false)
    // History intentionally preserved (Wireframe §4 / TRD-UI-5).
  }, [])

  const handleMinimize = useCallback(() => {
    setOpen(false)
  }, [])

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed) return
      setShowSampleChip(false)
      setShowFirstOpenHint(false)
      setComposer('')
      isNearBottomRef.current = true
      setShowJumpDown(false)
      await chat.ask(trimmed)
    },
    [chat],
  )

  const handleComposerSubmit = useCallback(() => {
    void send(composer)
  }, [composer, send])

  // Smart auto-scroll (Wireframe §4.8): only follow the bottom when the
  // tester is already near the bottom; otherwise show a jump-down chip.
  useEffect(() => {
    const el = bodyRef.current
    if (!el) return
    if (isNearBottomRef.current) {
      el.scrollTop = el.scrollHeight
      setShowJumpDown(false)
    } else {
      setShowJumpDown(true)
    }
  }, [chat.rows, chat.pending])

  const handleScroll = useCallback(() => {
    const el = bodyRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    isNearBottomRef.current = distanceFromBottom <= NEAR_BOTTOM_PX
    if (isNearBottomRef.current) setShowJumpDown(false)
  }, [])

  const jumpToBottom = useCallback(() => {
    const el = bodyRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
    isNearBottomRef.current = true
    setShowJumpDown(false)
  }, [])

  const handleSignOut = useCallback(() => {
    chat.reset()
    signOut()
    setOpen(false)
    setComposer('')
    setShowSampleChip(true)
    setShowFirstOpenHint(false)
    navigate('/login', { replace: true })
  }, [chat, navigate, signOut])

  const inputDisabled = chat.pending || !token

  return (
    <>
      <AvatarTrigger
        onClick={handleOpen}
        hidden={open}
        buttonRef={fabRef}
      />

      <Modal
        open={open}
        onClose={handleClose}
        onMinimize={handleMinimize}
        signedInLabel={session?.email}
        returnFocusRef={fabRef}
        liveRegion={chat.liveRegionMessage}
        footer={
          <>
            <InputField
              value={composer}
              onChange={setComposer}
              onSubmit={handleComposerSubmit}
              disabled={inputDisabled}
              placeholder="Ask a closed-corpus policy question…"
              metaSlot={
                <>
                  {showSampleChip ? (
                    <button
                      type="button"
                      onClick={() => void send(SAMPLE_PROMPT)}
                      disabled={inputDisabled}
                      title="Send the suggested pilot prompt"
                    >
                      Try the sample prompt
                    </button>
                  ) : (
                    <span />
                  )}
                  <button
                    type="button"
                    onClick={handleSignOut}
                    title="Sign out and clear this session"
                  >
                    Sign out
                  </button>
                </>
              }
            />
            {chat.status ? (
              <p className="pilot-status" role="status">
                {chat.status}
              </p>
            ) : null}
          </>
        }
      >
        <div
          ref={bodyRef}
          className="pilot-modal-body"
          role="log"
          aria-live="polite"
          onScroll={handleScroll}
        >
          {showFirstOpenHint && chat.rows.length === 0 ? (
            <p className="pilot-hint">
              Ask anything about BPL policies — answers come from Selvon’s
              curated docs.
            </p>
          ) : null}

          <PilotTranscript
            rows={chat.rows}
            pending={chat.pending}
            onFeedback={chat.submitFeedback}
            onOpenCitation={chat.openCitation}
          />
        </div>

        {showJumpDown ? (
          <button
            type="button"
            className="pilot-jump-down"
            onClick={jumpToBottom}
          >
            ↓ new message
          </button>
        ) : null}
      </Modal>
    </>
  )
}
