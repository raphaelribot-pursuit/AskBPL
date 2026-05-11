export type AvatarStateName =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'retrieving'
  | 'answering'
  | 'success'
  | 'refusalOutOfCorpus'
  | 'refusalPII'
  | 'routing'
  | 'greeting'
  | 'goodbye'
  | 'error'
  | 'dragging'
  | 'minimized'

export type AvatarEvent =
  | { type: 'INPUT_FOCUSED' }
  | { type: 'INPUT_BLURRED' }
  | { type: 'REQUEST_SUBMITTED' }
  | { type: 'RETRIEVAL_STARTED' }
  | { type: 'GENERATION_STARTED' }
  | { type: 'RESPONSE_SUCCESS' }
  | { type: 'RESPONSE_REFUSAL_CORPUS' }
  | { type: 'RESPONSE_REFUSAL_PII' }
  | { type: 'RESPONSE_ROUTING' }
  | { type: 'RESPONSE_ERROR' }
  | { type: 'MODAL_OPENED'; firstThisSession: boolean }
  | { type: 'MODAL_CLOSING' }
  | { type: 'DRAG_START' }
  | { type: 'DRAG_END' }
  | { type: 'MINIMIZE'; mode: MinimizeMode }
  | { type: 'RESTORE' }
  | { type: 'DEV_FORCE'; state: AvatarStateName }
  | { type: 'SET_REDUCED_MOTION'; reducedMotion: boolean }

export type MinimizeMode = 'none' | 'pill' | 'dock'

export type AvatarPosition = { x: number; y: number }

export type DockSide = 'left' | 'right'

export type QueuedOutcome = 'success' | 'refusalOutOfCorpus' | 'refusalPII' | 'error' | null
