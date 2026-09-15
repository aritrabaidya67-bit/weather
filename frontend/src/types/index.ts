/**
 * Types mirroring the FastAPI schemas. They are hand written (rather than
 * generated) so the UI contract stays explicit and reviewable, and every
 * nullable field is nullable here too: the UI must cope with partial data.
 */

export type Severity = "good" | "info" | "watch" | "warning" | "critical" | "unknown";
export type TrendDirection = "rising" | "falling" | "stable" | "unknown";
export type AlertSeverity = "info" | "warning" | "critical";
export type DataSource = "arduino" | "api" | "manual" | "none" | "unknown";

export interface SensorSpec {
  key: string;
  label: string;
  unit: string;
  kind: "numeric" | "status";
  minimum: number | null;
  maximum: number | null;
  decimals: number;
  color: string;
  description: string;
  channel: string | null;
  calibration_notes: string;
  bands: { until: number; label: string; severity: Severity }[];
}

export interface ChannelSpec {
  key: string;
  label: string;
  primary: string;
  secondary: string[];
  sensor: string;
  icon: string;
}

export interface RiskLevelInfo {
  level: number;
  code: string;
  label: string;
  min_score: number;
  max_score: number;
  description: string;
  color: string;
  led_index: number;
  buzzer_pattern: string;
}

export interface RiskModel {
  version: string;
  description: string;
  levels: RiskLevelInfo[];
  factors: {
    key: string;
    label: string;
    weight: number;
    metric: string | null;
    bands: { until: number; points: number; reason: string | null }[];
    note: string | null;
  }[];
  weights: Record<string, number>;
  combination_rules: { id: string; label: string; reason: string; points: number }[];
  notes: string[];
}

export interface MetaResponse {
  app_name: string;
  version: string;
  environment: string;
  server_time: string;
  api_version: string;
  risk_model: RiskModel;
  sensors: SensorSpec[];
  channels: ChannelSpec[];
  alert_rules: AlertRule[];
  features: Record<string, boolean | number | string>;
  local_addresses: string[];
  recommended_backend_url: string | null;
}

export interface RiskContribution {
  key: string;
  label: string;
  points: number;
  max_points: number;
  weight: number;
  normalised: number;
  reading: number | null;
  unit: string | null;
  severity: Severity;
  reason: string | null;
  direction: "increasing" | "reducing" | "neutral";
}

export interface RiskAssessment {
  score: number;
  level: number;
  label: string;
  code: string;
  color: string;
  description: string;
  confidence: number;
  reasons: string[];
  reducing_factors: string[];
  recommended_actions: string[];
  contributions: RiskContribution[];
  data_coverage: number;
  missing_metrics: string[];
  model_version: string;
  evaluated_at: string | null;
  context: Record<string, unknown> & {
    source?: string;
    health_score?: number;
    stale?: boolean;
    data_age_seconds?: number | null;
    heat_index_c?: number | null;
    led_index?: number;
    buzzer_pattern?: string;
  };
}

export interface Anomaly {
  sensor: string;
  label: string;
  unit: string;
  severity: "low" | "medium" | "high";
  kind: "spike" | "drop" | "sudden_change" | "stuck" | "out_of_range";
  current_value: number;
  expected_value: number | null;
  expected_low: number | null;
  expected_high: number | null;
  deviation: number | null;
  z_score: number | null;
  baseline_samples: number;
  message: string;
  explanation: string;
  detected_at: string;
  direction: "above" | "below";
  contribution_to_risk: number;
}

export interface Reading {
  id: number | null;
  device_id: string;
  timestamp: string;
  received_at: string;
  source: DataSource;
  temperature_c: number | null;
  humidity_pct: number | null;
  bmp_temperature_c: number | null;
  pressure_hpa: number | null;
  rain_raw: number | null;
  rain_pct: number | null;
  ldr_raw: number | null;
  light_pct: number | null;
  air_quality_raw: number | null;
  air_quality_index: number | null;
  heat_index_c: number | null;
  dew_point_c: number | null;
  rain_status: string | null;
  light_status: string | null;
  air_quality_status: string | null;
  risk_score: number | null;
  risk_level: number | null;
  risk_label: string | null;
  risk_reasons: string[] | null;
  recommended_actions: string[] | null;
  risk_factors: RiskContribution[] | null;
  anomalies: Anomaly[] | null;
  health_score: number | null;
  is_stale?: boolean;
  age_seconds?: number | null;
  missing_metrics?: string[];
}

export interface SeriesPoint {
  timestamp: string;
  value: number | null;
  risk_score?: number | null;
  risk_level?: number | null;
}

export interface MetricSeries {
  metric: string;
  label: string;
  unit: string;
  points: SeriesPoint[];
  minimum: number | null;
  maximum: number | null;
  mean: number | null;
  median: number | null;
  p95: number | null;
  stdev: number | null;
  latest: number | null;
  change: number | null;
  change_pct: number | null;
  slope_per_minute: number | null;
  trend: TrendDirection;
  sample_count: number;
  r_squared: number | null;
}

export interface ChannelCard {
  channel: string;
  label: string;
  sensor: string;
  icon: string;
  metric: string;
  unit: string;
  color: string;
  decimals: number;
  value: number | null;
  status: string;
  severity: Severity;
  trend: TrendDirection;
  change: number | null;
  change_pct: number | null;
  sufficient_data: boolean;
  sample_count: number;
  sparkline: SeriesPoint[];
  stats: {
    min: number | null;
    max: number | null;
    mean: number | null;
    median: number | null;
    stdev: number | null;
    p95: number | null;
    slope_per_minute: number | null;
    r_squared: number | null;
  };
  secondary: Record<string, { label: string; unit: string; latest: number; mean: number | null }>;
  rate_of_change_per_hour: number | null;
  stale: boolean;
}

export interface SensorHealth {
  key: string;
  label: string;
  channel: string | null;
  status: "ok" | "degraded" | "stale" | "suspect" | "failed" | "unknown";
  last_value: number | null;
  unit: string | null;
  last_seen_at: string | null;
  age_seconds: number | null;
  expected_rate_per_minute: number | null;
  observed_rate_per_minute: number | null;
  coverage_pct: number | null;
  message: string | null;
}

export interface Observation {
  id: string;
  kind: string;
  importance: "critical" | "warning" | "notice" | "info";
  text: string;
  evidence: Record<string, unknown>;
  generated_from: string;
}

export interface DeviceSummary {
  device_id: string;
  display_name?: string | null;
  online: boolean;
  status: string;
  status_message: string;
  last_seen_at: string | null;
  seconds_since_last_payload: number | null;
  firmware_version?: string | null;
  ip_address?: string | null;
  source?: DataSource;
  latest_reading_id?: number | null;
}

export interface DeviceStatus {
  device_id: string;
  display_name: string | null;
  online: boolean;
  status: string;
  status_message: string;
  source: DataSource;
  firmware_version: string | null;
  ip_address: string | null;
  rssi: number | null;
  rssi_quality: string | null;
  uptime_ms: number | null;
  uptime_human: string | null;
  transmission_interval_ms: number | null;
  transmission_interval_seconds: number | null;
  expected_interval_seconds: number | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  last_payload_at: string | null;
  seconds_since_last_payload: number | null;
  total_readings: number;
  rejected_payloads: number;
  missed_intervals: number;
  estimated_delivery_rate_pct: number | null;
  sensors_available: string[];
  sensors_missing: string[];
  sensor_health: SensorHealth[];
  last_risk_score: number | null;
  last_risk_level: number | null;
  last_reading_at: string | null;
  notes: string[];
}

export interface Alert {
  id: number | null;
  fingerprint: string | null;
  device_id: string | null;
  category: string;
  severity: AlertSeverity | string;
  title: string;
  message: string;
  sensor: string | null;
  metric_value: number | null;
  risk_level: number | null;
  recommended_action: string | null;
  context: Record<string, unknown> | null;
  is_active: boolean;
  occurrence_count: number;
  triggered_at: string | null;
  last_seen_at: string | null;
  resolved_at: string | null;
  acknowledged_at: string | null;
}

export interface AlertList {
  device_id: string;
  active_count: number;
  total_count: number;
  severity_counts: Record<string, number>;
  category_counts: Record<string, number>;
  alerts: Alert[];
  notes: string[];
}

export interface AlertRule {
  id: string;
  category: string;
  severity: string;
  title: string;
  description: string;
  condition: string;
  default_action: string;
  enabled: boolean;
}

export interface MetricPrediction {
  metric: string;
  label: string;
  unit: string;
  current_value: number | null;
  predicted_value: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
  delta: number | null;
  direction: TrendDirection;
  horizon_minutes: number;
  confidence: number;
  confidence_label: "low" | "medium" | "high";
  method: string;
  samples_used: number;
  r_squared: number | null;
  expected_status: string | null;
  current_status: string | null;
  reasoning: string;
  features: string[];
  warnings: string[];
}

export interface RiskForecast {
  horizon_minutes: number;
  current_score: number | null;
  predicted_score: number | null;
  current_level: number | null;
  predicted_level: number | null;
  predicted_label: string | null;
  direction: TrendDirection;
  confidence: number;
  drivers: string[];
}

export interface RainForecast {
  horizon_minutes: number;
  probability: number;
  confidence: number;
  method: string;
  reasoning: string;
  currently_raining: boolean;
  inputs?: Record<string, number>;
}

export interface PredictionResponse {
  device_id: string;
  generated_at: string;
  primary_horizon_minutes: number;
  horizons_minutes: number[];
  data_sufficient: boolean;
  samples_used: number;
  observation_window_minutes: number;
  metrics: Record<string, MetricPrediction>;
  all_horizons: Record<string, Record<string, MetricPrediction | RiskForecast>>;
  risk: RiskForecast | null;
  rain: RainForecast | null;
  summary: string[];
  notes: string[];
  disclaimer: string;
}

export interface PredictionAccuracy {
  device_id: string;
  evaluated_count: number;
  horizons: Record<string, Record<string, number | null>>;
  notes: string[];
}

export interface Overview {
  device_id: string;
  server_time: string;
  range_hours: number;
  reading_count: number;
  has_data: boolean;
  data_source: DataSource;
  stale: boolean;
  latest: Partial<Reading>;
  metrics: Record<string, number | null>;
  channels: ChannelCard[];
  risk: RiskAssessment;
  anomalies: Anomaly[];
  anomaly_counts: Record<string, number>;
  alerts: Alert[];
  active_alert_count: number;
  observation_list: Observation[];
  classification: { label: string; components: Record<string, number | null>; heat_stress: string };
  correlations: { left: string; right: string; r: number; samples: number; hours: number; message: string }[];
  sensor_health: SensorHealth[];
  device: DeviceSummary;
  heat_index_c: number | null;
  dew_point_c: number | null;
  sufficient_history: boolean;
  notes: string[];
}

export interface HistoryResponse {
  device_id: string;
  range_hours: number;
  bucket: string | null;
  count: number;
  from_timestamp: string | null;
  to_timestamp: string | null;
  readings: Reading[];
  series: Record<string, MetricSeries>;
  sufficient_data: boolean;
  notes: string[];
}

export interface SystemStatus {
  server_time: string;
  backend: string;
  database: string;
  arduino: string;
  device_online: boolean;
  device_last_seen_at: string | null;
  device_seconds_since_payload: number | null;
  reading_stale: boolean;
  realtime_subscribers: number;
  data_source: DataSource;
  ollama: OllamaStatus;
  active_alerts: number;
  chat_rate_limit_per_minute: number;
  notes: string[];
}

export interface OllamaStatus {
  available: boolean;
  host: string;
  model: string | null;
  models_available: string[];
  installed: boolean;
  running: boolean;
  detail: string;
  binary_path?: string | null;
  models_directory?: string | null;
  context_chars?: number;
  generated_at?: string;
}

export interface ChatCitation {
  label: string;
  value: string;
  source: string;
  timestamp: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  model?: string | null;
  fallbackUsed?: boolean;
  warning?: string | null;
  citations?: ChatCitation[];
  latencyMs?: number | null;
  streaming?: boolean;
  error?: boolean;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  model: string | null;
  grounding: string;
  data_available: boolean;
  used_context: Record<string, unknown>;
  citations: ChatCitation[];
  latency_ms: number | null;
  fallback_used: boolean;
  warning: string | null;
  created_at: string;
}

export interface RiskState {
  device_id: string;
  risk_score: number;
  risk_level: number;
  risk_label: string;
  risk_code: string;
  color: string;
  led_index: number;
  buzzer_pattern: string;
  reasons: string[];
  recommended_actions: string[];
  stale: boolean;
  age_seconds: number | null;
  data_source: string;
  evaluated_at: string | null;
  alerts_active: number;
  server_time: string;
}

export interface SummaryResponse {
  device_id: string;
  period: string;
  from_timestamp: string | null;
  to_timestamp: string | null;
  reading_count: number;
  coverage_pct: number | null;
  metrics: Record<string, Record<string, number | string | null>>;
  risk: Record<string, unknown>;
  alerts: Record<string, number>;
  anomalies_by_sensor: Record<string, number>;
  highlights: string[];
}

export interface WorkerStatus {
  background: {
    enabled: boolean;
    jobs: string[];
    last_runs: Record<string, string>;
    counters: Record<string, number>;
  };
  realtime_subscribers: number;
  rules_loaded: number;
}

/** Realtime bus envelope. */
export interface RealtimeEvent {
  id: number;
  topic: "reading" | "risk" | "anomaly" | "alert" | "prediction" | "device" | "system";
  timestamp: string;
  data: Record<string, unknown>;
}
