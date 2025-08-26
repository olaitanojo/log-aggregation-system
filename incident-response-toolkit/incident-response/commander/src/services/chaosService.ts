import axios from 'axios';
import { ChaosExperiment, ExperimentTemplate, ExperimentType } from '../types/chaos';

const API_BASE_URL = process.env.REACT_APP_CHAOS_API_URL || '/chaos-api';

class ChaosService {
  private api = axios.create({
    baseURL: API_BASE_URL,
    timeout: 15000,
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
  }

  async getExperiments(): Promise<ChaosExperiment[]> {
    const response = await this.api.get('/experiments');
    return response.data.map(this.transformExperiment);
  }

  async getActiveExperiments(): Promise<ChaosExperiment[]> {
    const response = await this.api.get('/experiments/active');
    return response.data.map(this.transformExperiment);
  }

  async getExperiment(id: string): Promise<ChaosExperiment> {
    const response = await this.api.get(`/experiments/${id}`);
    return this.transformExperiment(response.data);
  }

  async createExperiment(experiment: Partial<ChaosExperiment>): Promise<ChaosExperiment> {
    const response = await this.api.post('/experiments', experiment);
    return this.transformExperiment(response.data);
  }

  async updateExperiment(id: string, updates: Partial<ChaosExperiment>): Promise<ChaosExperiment> {
    const response = await this.api.put(`/experiments/${id}`, updates);
    return this.transformExperiment(response.data);
  }

  async deleteExperiment(id: string): Promise<void> {
    await this.api.delete(`/experiments/${id}`);
  }

  async startExperiment(id: string): Promise<void> {
    await this.api.post(`/experiments/${id}/start`);
  }

  async stopExperiment(id: string): Promise<void> {
    await this.api.post(`/experiments/${id}/stop`);
  }

  async cancelExperiment(id: string): Promise<void> {
    await this.api.post(`/experiments/${id}/cancel`);
  }

  async getExperimentLogs(id: string): Promise<string[]> {
    const response = await this.api.get(`/experiments/${id}/logs`);
    return response.data;
  }

  async getExperimentMetrics(id: string): Promise<any> {
    const response = await this.api.get(`/experiments/${id}/metrics`);
    return response.data;
  }

  async getTemplates(): Promise<ExperimentTemplate[]> {
    const response = await this.api.get('/templates');
    return response.data;
  }

  async createFromTemplate(templateId: string, customizations: any): Promise<ChaosExperiment> {
    const response = await this.api.post(`/templates/${templateId}/create`, customizations);
    return this.transformExperiment(response.data);
  }

  async validateTarget(target: any): Promise<{ valid: boolean; message?: string }> {
    const response = await this.api.post('/experiments/validate-target', { target });
    return response.data;
  }

  async getTargetInfo(target: any): Promise<any> {
    const response = await this.api.post('/experiments/target-info', { target });
    return response.data;
  }

  async scheduleExperiment(id: string, schedule: any): Promise<void> {
    await this.api.post(`/experiments/${id}/schedule`, { schedule });
  }

  async unscheduleExperiment(id: string): Promise<void> {
    await this.api.delete(`/experiments/${id}/schedule`);
  }

  async getExperimentsByType(type: ExperimentType): Promise<ChaosExperiment[]> {
    const response = await this.api.get(`/experiments?type=${type}`);
    return response.data.map(this.transformExperiment);
  }

  async getExperimentHistory(limit: number = 50): Promise<ChaosExperiment[]> {
    const response = await this.api.get(`/experiments/history?limit=${limit}`);
    return response.data.map(this.transformExperiment);
  }

  async rollbackExperiment(id: string): Promise<void> {
    await this.api.post(`/experiments/${id}/rollback`);
  }

  async getBlastRadiusPreview(experiment: Partial<ChaosExperiment>): Promise<any> {
    const response = await this.api.post('/experiments/blast-radius-preview', experiment);
    return response.data;
  }

  async getSafetyStatus(id: string): Promise<any> {
    const response = await this.api.get(`/experiments/${id}/safety`);
    return response.data;
  }

  // Transform API response to match frontend types
  private transformExperiment(data: any): ChaosExperiment {
    return {
      ...data,
      created_at: new Date(data.created_at),
      started_at: data.started_at ? new Date(data.started_at) : undefined,
      completed_at: data.completed_at ? new Date(data.completed_at) : undefined,
      results: data.results ? {
        ...data.results,
        start_time: new Date(data.results.start_time),
        end_time: new Date(data.results.end_time),
        safety_triggers: data.results.safety_triggers?.map((trigger: any) => ({
          ...trigger,
          triggered_at: new Date(trigger.triggered_at),
        })) || [],
      } : undefined,
    };
  }
}

export const chaosService = new ChaosService();
