import axios from 'axios';
import { 
  Incident, 
  IncidentStats, 
  CreateIncidentRequest, 
  UpdateIncidentRequest, 
  IncidentFilter 
} from '../types/incident';

const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

class IncidentService {
  private api = axios.create({
    baseURL: API_BASE_URL,
    timeout: 10000,
  });

  constructor() {
    // Add auth token to requests
    this.api.interceptors.request.use((config) => {
      const token = localStorage.getItem('auth_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Handle auth errors
    this.api.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem('auth_token');
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  async getStats(): Promise<IncidentStats> {
    const response = await this.api.get('/incidents/stats');
    return response.data;
  }

  async getIncidents(filter?: IncidentFilter): Promise<Incident[]> {
    const response = await this.api.get('/incidents', { params: filter });
    return response.data.map(this.transformIncident);
  }

  async getRecent(limit: number = 10): Promise<Incident[]> {
    const response = await this.api.get(`/incidents/recent?limit=${limit}`);
    return response.data.map(this.transformIncident);
  }

  async getIncident(id: string): Promise<Incident> {
    const response = await this.api.get(`/incidents/${id}`);
    return this.transformIncident(response.data);
  }

  async createIncident(data: CreateIncidentRequest): Promise<Incident> {
    const response = await this.api.post('/incidents', data);
    return this.transformIncident(response.data);
  }

  async updateIncident(id: string, data: UpdateIncidentRequest): Promise<Incident> {
    const response = await this.api.put(`/incidents/${id}`, data);
    return this.transformIncident(response.data);
  }

  async deleteIncident(id: string): Promise<void> {
    await this.api.delete(`/incidents/${id}`);
  }

  async addComment(id: string, message: string): Promise<void> {
    await this.api.post(`/incidents/${id}/comments`, { message });
  }

  async assignIncident(id: string, userId: string): Promise<void> {
    await this.api.post(`/incidents/${id}/assign`, { user_id: userId });
  }

  async escalateIncident(id: string): Promise<void> {
    await this.api.post(`/incidents/${id}/escalate`);
  }

  async resolveIncident(id: string, resolution: string): Promise<void> {
    await this.api.post(`/incidents/${id}/resolve`, { resolution });
  }

  async closeIncident(id: string): Promise<void> {
    await this.api.post(`/incidents/${id}/close`);
  }

  async executeRunbook(incidentId: string, runbookId: string): Promise<void> {
    await this.api.post(`/incidents/${incidentId}/runbooks`, { runbook_id: runbookId });
  }

  async sendCommunication(
    incidentId: string, 
    channel: string, 
    recipient: string, 
    message: string,
    subject?: string
  ): Promise<void> {
    await this.api.post(`/incidents/${incidentId}/communications`, {
      channel,
      recipient,
      message,
      subject,
    });
  }

  async getMetrics(id: string): Promise<any> {
    const response = await this.api.get(`/incidents/${id}/metrics`);
    return response.data;
  }

  // Transform API response to match frontend types
  private transformIncident(data: any): Incident {
    return {
      ...data,
      createdAt: new Date(data.created_at),
      updatedAt: new Date(data.updated_at),
      resolvedAt: data.resolved_at ? new Date(data.resolved_at) : undefined,
      timeline: data.timeline?.map((event: any) => ({
        ...event,
        timestamp: new Date(event.timestamp),
      })) || [],
      communications: data.communications?.map((comm: any) => ({
        ...comm,
        timestamp: new Date(comm.timestamp),
      })) || [],
      runbooks: data.runbooks?.map((runbook: any) => ({
        ...runbook,
        started_at: new Date(runbook.started_at),
        completed_at: runbook.completed_at ? new Date(runbook.completed_at) : undefined,
      })) || [],
    };
  }
}

export const incidentService = new IncidentService();
