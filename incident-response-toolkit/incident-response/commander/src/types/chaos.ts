export interface ChaosExperiment {
  id: string;
  name: string;
  description: string;
  type: ExperimentType;
  status: ExperimentStatus;
  created_at: Date;
  started_at?: Date;
  completed_at?: Date;
  duration: number; // seconds
  target: ExperimentTarget;
  parameters: ExperimentParameters;
  safety_rules: SafetyRule[];
  results?: ExperimentResults;
  created_by: string;
  scheduled?: ScheduleConfig;
}

export type ExperimentType = 
  | 'CPU_STRESS'
  | 'MEMORY_STRESS' 
  | 'DISK_STRESS'
  | 'NETWORK_LATENCY'
  | 'NETWORK_LOSS'
  | 'POD_KILLER'
  | 'NODE_KILLER'
  | 'SERVICE_KILLER'
  | 'DNS_CHAOS'
  | 'TIME_SKEW'
  | 'CUSTOM';

export type ExperimentStatus = 
  | 'DRAFT'
  | 'SCHEDULED'
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'ROLLED_BACK';

export interface ExperimentTarget {
  type: TargetType;
  selector: TargetSelector;
  scope: TargetScope;
}

export type TargetType = 'KUBERNETES' | 'DOCKER' | 'SYSTEM' | 'NETWORK' | 'APPLICATION';

export interface TargetSelector {
  namespace?: string;
  labels?: Record<string, string>;
  names?: string[];
  percentage?: number; // For partial targeting
}

export interface TargetScope {
  cluster?: string;
  region?: string;
  environment: string; // dev, staging, prod
}

export interface ExperimentParameters {
  [key: string]: any;
  
  // CPU Stress
  cpu_percent?: number;
  cpu_workers?: number;
  
  // Memory Stress  
  memory_percent?: number;
  memory_size?: string; // e.g., "1GB"
  
  // Network
  latency_ms?: number;
  packet_loss_percent?: number;
  bandwidth_limit?: string; // e.g., "1Mbps"
  
  // Chaos
  kill_signal?: string;
  grace_period?: number;
}

export interface SafetyRule {
  id: string;
  name: string;
  type: SafetyRuleType;
  condition: SafetyCondition;
  action: SafetyAction;
  enabled: boolean;
}

export type SafetyRuleType = 
  | 'METRIC_THRESHOLD'
  | 'ERROR_RATE'
  | 'RESPONSE_TIME'
  | 'AVAILABILITY'
  | 'CUSTOM_QUERY';

export interface SafetyCondition {
  metric: string;
  operator: 'GT' | 'LT' | 'EQ' | 'GTE' | 'LTE';
  value: number;
  duration: number; // seconds to maintain condition before triggering
}

export type SafetyAction = 'STOP_EXPERIMENT' | 'ROLLBACK' | 'ALERT' | 'SCALE_UP';

export interface ExperimentResults {
  success: boolean;
  start_time: Date;
  end_time: Date;
  duration: number;
  impact_assessment: ImpactAssessment;
  metrics: ExperimentMetrics;
  logs: string[];
  safety_triggers?: SafetyTrigger[];
}

export interface ImpactAssessment {
  blast_radius: BlastRadius;
  service_impact: ServiceImpact[];
  user_impact: UserImpact;
  performance_impact: PerformanceImpact;
}

export interface BlastRadius {
  affected_services: string[];
  affected_instances: number;
  affected_regions: string[];
  total_scope_percentage: number;
}

export interface ServiceImpact {
  service_name: string;
  availability_change: number; // percentage change
  error_rate_change: number;   // percentage change
  latency_change: number;      // milliseconds change
}

export interface UserImpact {
  affected_users: number;
  user_experience_score: number; // 1-10 scale
  complaints: number;
}

export interface PerformanceImpact {
  cpu_usage_change: number;
  memory_usage_change: number;
  disk_usage_change: number;
  network_usage_change: number;
}

export interface ExperimentMetrics {
  [key: string]: MetricTimeseries;
}

export interface MetricTimeseries {
  metric_name: string;
  values: MetricValue[];
  unit: string;
}

export interface MetricValue {
  timestamp: Date;
  value: number;
}

export interface SafetyTrigger {
  rule_id: string;
  rule_name: string;
  triggered_at: Date;
  action_taken: SafetyAction;
  condition_met: string;
}

export interface ScheduleConfig {
  enabled: boolean;
  cron_expression: string;
  timezone: string;
  max_runs?: number;
  end_date?: Date;
}

export interface ExperimentTemplate {
  id: string;
  name: string;
  description: string;
  type: ExperimentType;
  default_parameters: ExperimentParameters;
  default_duration: number;
  safety_rules: SafetyRule[];
  tags: string[];
  documentation: string;
}
