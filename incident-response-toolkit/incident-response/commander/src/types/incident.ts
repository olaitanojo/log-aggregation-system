export interface Incident {
  id: string;
  title: string;
  description: string;
  severity: SeverityLevel;
  status: IncidentStatus;
  createdAt: Date;
  updatedAt: Date;
  resolvedAt?: Date;
  assignedTo?: User;
  commander?: User;
  team: string;
  services: string[];
  tags: string[];
  timeline: TimelineEvent[];
  communications: Communication[];
  runbooks: RunbookExecution[];
  metrics: IncidentMetrics;
}

export type SeverityLevel = 'SEV1' | 'SEV2' | 'SEV3' | 'SEV4';

export type IncidentStatus = 
  | 'OPEN' 
  | 'INVESTIGATING' 
  | 'IDENTIFIED' 
  | 'MONITORING' 
  | 'RESOLVED' 
  | 'CLOSED';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  phone?: string;
  slack_id?: string;
  teams_id?: string;
}

export type UserRole = 'ENGINEER' | 'SRE' | 'MANAGER' | 'INCIDENT_COMMANDER';

export interface TimelineEvent {
  id: string;
  timestamp: Date;
  type: TimelineEventType;
  user: User;
  message: string;
  metadata?: Record<string, any>;
}

export type TimelineEventType = 
  | 'CREATED'
  | 'STATUS_CHANGE'
  | 'SEVERITY_CHANGE'
  | 'ASSIGNMENT_CHANGE'
  | 'COMMENT'
  | 'RUNBOOK_EXECUTED'
  | 'COMMUNICATION_SENT'
  | 'RESOLVED'
  | 'CLOSED';

export interface Communication {
  id: string;
  timestamp: Date;
  channel: CommunicationChannel;
  recipient: string;
  subject?: string;
  message: string;
  status: CommunicationStatus;
  user: User;
}

export type CommunicationChannel = 'SLACK' | 'EMAIL' | 'SMS' | 'TEAMS' | 'PHONE';
export type CommunicationStatus = 'PENDING' | 'SENT' | 'DELIVERED' | 'FAILED';

export interface RunbookExecution {
  id: string;
  runbook_id: string;
  runbook_name: string;
  status: RunbookStatus;
  started_at: Date;
  completed_at?: Date;
  user: User;
  steps: RunbookStep[];
  output?: string;
  error?: string;
}

export type RunbookStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export interface RunbookStep {
  id: string;
  name: string;
  status: RunbookStatus;
  command?: string;
  output?: string;
  error?: string;
  started_at?: Date;
  completed_at?: Date;
}

export interface IncidentMetrics {
  detection_time?: number;      // Time from incident start to detection (minutes)
  response_time?: number;       // Time from detection to first response (minutes)
  resolution_time?: number;     // Time from detection to resolution (minutes)
  mttr?: number;               // Mean Time To Repair (minutes)
  affected_users?: number;     // Number of users affected
  downtime?: number;           // Total downtime in minutes
  business_impact?: string;    // Business impact assessment
}

export interface CreateIncidentRequest {
  title: string;
  description: string;
  severity: SeverityLevel;
  team: string;
  services: string[];
  tags?: string[];
  commander_id?: string;
}

export interface UpdateIncidentRequest {
  title?: string;
  description?: string;
  severity?: SeverityLevel;
  status?: IncidentStatus;
  assigned_to?: string;
  commander_id?: string;
  team?: string;
  services?: string[];
  tags?: string[];
}

export interface IncidentFilter {
  status?: IncidentStatus[];
  severity?: SeverityLevel[];
  team?: string[];
  assignee?: string[];
  dateRange?: {
    start: Date;
    end: Date;
  };
  search?: string;
}

export interface IncidentStats {
  total: number;
  open: number;
  resolved_today: number;
  avg_resolution_time: number;
  mttr_trend: number[];
  severity_distribution: Record<SeverityLevel, number>;
  team_distribution: Record<string, number>;
}
