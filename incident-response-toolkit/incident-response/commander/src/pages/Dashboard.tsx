import React, { useState, useEffect } from 'react';
import {
  Grid,
  Card,
  CardContent,
  Typography,
  Box,
  CircularProgress,
  Alert,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Button,
} from '@mui/material';
import {
  Warning,
  Error,
  CheckCircle,
  TrendingUp,
  People,
  Schedule,
  BugReport,
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

import { Incident, IncidentStats, SeverityLevel } from '../types/incident';
import { ChaosExperiment } from '../types/chaos';
import { incidentService } from '../services/incidentService';
import { chaosService } from '../services/chaosService';

const severityColors: Record<SeverityLevel, string> = {
  SEV1: '#f44336',
  SEV2: '#ff9800', 
  SEV3: '#2196f3',
  SEV4: '#4caf50',
};

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<IncidentStats | null>(null);
  const [recentIncidents, setRecentIncidents] = useState<Incident[]>([]);
  const [activeExperiments, setActiveExperiments] = useState<ChaosExperiment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadDashboardData();
    
    // Set up real-time updates
    const interval = setInterval(loadDashboardData, 30000); // Update every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [statsData, incidentsData, experimentsData] = await Promise.all([
        incidentService.getStats(),
        incidentService.getRecent(10),
        chaosService.getActiveExperiments(),
      ]);
      
      setStats(statsData);
      setRecentIncidents(incidentsData);
      setActiveExperiments(experimentsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  const getSeverityChip = (severity: SeverityLevel) => (
    <Chip 
      label={severity} 
      size="small"
      sx={{ 
        backgroundColor: severityColors[severity],
        color: 'white',
        fontWeight: 'bold'
      }}
    />
  );

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'OPEN': return '#f44336';
      case 'INVESTIGATING': return '#ff9800';
      case 'IDENTIFIED': return '#2196f3';
      case 'MONITORING': return '#9c27b0';
      case 'RESOLVED': return '#4caf50';
      case 'CLOSED': return '#757575';
      default: return '#757575';
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="400px">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" action={
        <Button color="inherit" size="small" onClick={loadDashboardData}>
          Retry
        </Button>
      }>
        {error}
      </Alert>
    );
  }

  const mttrTrendData = stats?.mttr_trend.map((value, index) => ({
    day: `Day ${index + 1}`,
    mttr: value,
  })) || [];

  const severityDistribution = stats ? Object.entries(stats.severity_distribution).map(([severity, count]) => ({
    name: severity,
    value: count,
    color: severityColors[severity as SeverityLevel],
  })) : [];

  return (
    <Box p={3}>
      <Typography variant="h4" gutterBottom>
        Incident Response Dashboard
      </Typography>

      {/* Key Metrics */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <Warning color="warning" sx={{ mr: 2 }} />
                <Box>
                  <Typography variant="h4">{stats?.open || 0}</Typography>
                  <Typography color="textSecondary">Open Incidents</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <CheckCircle color="success" sx={{ mr: 2 }} />
                <Box>
                  <Typography variant="h4">{stats?.resolved_today || 0}</Typography>
                  <Typography color="textSecondary">Resolved Today</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <Schedule color="primary" sx={{ mr: 2 }} />
                <Box>
                  <Typography variant="h4">{stats?.avg_resolution_time || 0}m</Typography>
                  <Typography color="textSecondary">Avg Resolution Time</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <BugReport color="secondary" sx={{ mr: 2 }} />
                <Box>
                  <Typography variant="h4">{activeExperiments.length}</Typography>
                  <Typography color="textSecondary">Active Experiments</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {/* MTTR Trend Chart */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Mean Time To Repair Trend (Last 7 Days)
              </Typography>
              <Box height={300}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={mttrTrendData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="day" />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="mttr" stroke="#8884d8" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Severity Distribution */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Incidents by Severity
              </Typography>
              <Box height={300}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={severityDistribution}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, value }) => `${name}: ${value}`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {severityDistribution.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Recent Incidents */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Recent Incidents
              </Typography>
              <List dense>
                {recentIncidents.map((incident) => (
                  <ListItem key={incident.id} divider>
                    <ListItemIcon>
                      {incident.severity === 'SEV1' ? (
                        <Error color="error" />
                      ) : incident.severity === 'SEV2' ? (
                        <Warning color="warning" />
                      ) : (
                        <Error color="info" />
                      )}
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        <Box display="flex" alignItems="center" gap={1}>
                          <Typography variant="subtitle2">{incident.title}</Typography>
                          {getSeverityChip(incident.severity)}
                          <Chip 
                            label={incident.status} 
                            size="small"
                            variant="outlined"
                            sx={{ color: getStatusColor(incident.status) }}
                          />
                        </Box>
                      }
                      secondary={
                        <Typography variant="caption" color="textSecondary">
                          {new Date(incident.createdAt).toLocaleString()}
                        </Typography>
                      }
                    />
                  </ListItem>
                ))}
                {recentIncidents.length === 0 && (
                  <ListItem>
                    <ListItemText primary="No recent incidents" />
                  </ListItem>
                )}
              </List>
            </CardContent>
          </Card>
        </Grid>

        {/* Active Chaos Experiments */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Active Chaos Experiments
              </Typography>
              <List dense>
                {activeExperiments.map((experiment) => (
                  <ListItem key={experiment.id} divider>
                    <ListItemIcon>
                      <BugReport color="secondary" />
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        <Box display="flex" alignItems="center" gap={1}>
                          <Typography variant="subtitle2">{experiment.name}</Typography>
                          <Chip 
                            label={experiment.status} 
                            size="small"
                            color={experiment.status === 'RUNNING' ? 'warning' : 'default'}
                          />
                        </Box>
                      }
                      secondary={
                        <Typography variant="caption" color="textSecondary">
                          {experiment.type} • {experiment.target.scope.environment}
                        </Typography>
                      }
                    />
                  </ListItem>
                ))}
                {activeExperiments.length === 0 && (
                  <ListItem>
                    <ListItemText primary="No active experiments" />
                  </ListItem>
                )}
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;
