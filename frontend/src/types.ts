export type SelectionPriority = 'multichannel' | 'fewer_errors' | 'closest_duration'

export interface JobRequest {
  mode: 'm' | 'f'
  source: string
  target: string
  logname: string
  duptype: 'case' | 'exact' | 'semantic' | 'both' | 'all'
  error_target: string | null
  novideo_target: string | null
  max_errors_when_mc: number
  max_duration_diff_longer: number
  max_duration_diff_shorter: number
  selection_priorities: SelectionPriority[]
  semantic_prefixes: string[]
  remove_episode_nos: boolean
}

export interface ProgressSnapshot {
  phase: string
  current_file: string | null
  current_dir: string | null
  dirs_completed: number
  dirs_total: number
  files_scanned: number
  groups_found: number
  files_planned: number
  files_moved: number
  total_files_to_move: number
}

export interface JobResult {
  files_scanned: number
  groups_found: number
  action_counts: Record<string, number>
  action_sizes: Record<string, number>
  log_path: string | null
}

export interface JobStatus {
  job_id: string
  state: 'pending' | 'scanning' | 'planning' | 'executing' | 'completed' | 'failed' | 'cancelled'
  progress: ProgressSnapshot | null
  result: JobResult | null
  error: string | null
}
