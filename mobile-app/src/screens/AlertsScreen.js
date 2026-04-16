import React, { useState, useEffect } from 'react';
import { View, StyleSheet, ScrollView, RefreshControl, SafeAreaView, Platform } from 'react-native';
import { Text, IconButton } from 'react-native-paper';
import { ShieldAlert, MapPin, Calendar, Clock, ChevronRight, HardDrive, ShieldCheck } from 'lucide-react-native';
import api from '../api';
import { theme } from '../styles/theme';

export default function AlertsScreen() {
  const [alerts, setAlerts] = useState([]);
  const [refreshing, setRefreshing] = useState(false);

  const loadAlerts = async () => {
    try {
      const response = await api.get('/alerts/my');
      setAlerts(response.data);
    } catch (error) {
      console.error('Failed to load alerts:', error);
    }
  };

  useEffect(() => {
    loadAlerts();
  }, []);

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true);
    await loadAlerts();
    setRefreshing(false);
  }, []);

  const getThreatColor = (level) => {
    switch (level) {
      case 'HIGH': return theme.colors.error;
      case 'MEDIUM': return theme.colors.accentAmber;
      case 'LOW': return theme.colors.accentAmber;
      default: return theme.colors.primary;
    }
  };

  return (
    <View style={styles.container}>
      <SafeAreaView style={styles.header}>
        <Text style={styles.title}>Safety Alerts</Text>
        <Text style={styles.subtitle}>Your security history</Text>
      </SafeAreaView>

      <ScrollView 
        contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={theme.colors.primary} />}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.statsSummary}>
           <View style={styles.summaryItem}>
              <Text style={styles.summaryLabel}>Total Alerts</Text>
              <Text style={styles.summaryValue}>{alerts.length}</Text>
           </View>
           <View style={styles.summaryDivider} />
           <View style={styles.summaryItem}>
              <Text style={styles.summaryLabel}>Status</Text>
              <Text style={[styles.summaryValue, { color: theme.colors.primary }]}>Protected</Text>
           </View>
           <View style={styles.summaryDivider} />
           <View style={styles.summaryItem}>
              <Text style={styles.summaryLabel}>Privacy</Text>
              <Text style={styles.summaryValue}>Encrypted</Text>
           </View>
        </View>

        {alerts.length === 0 ? (
          <View style={styles.empty}>
            <View style={styles.emptyIconCircle}>
               <ShieldCheck size={48} color={theme.colors.primary} />
            </View>
            <Text style={styles.emptyTitle}>Everything looks safe</Text>
            <Text style={styles.emptySub}>SafeSphere hasn't detected any threats during your recent journeys. You are well protected.</Text>
          </View>
        ) : (
          alerts.map(alert => (
            <TouchableOpacity key={alert.id} style={styles.alertItem} activeOpacity={0.7}>
               <View style={[styles.threatStripe, { backgroundColor: getThreatColor(alert.threat_level) }]} />
               <View style={styles.alertMain}>
                  <View style={styles.alertHeader}>
                     <View style={[styles.levelBadge, { backgroundColor: getThreatColor(alert.threat_level) + '20' }]}>
                        <Text style={[styles.levelText, { color: getThreatColor(alert.threat_level) }]}>{alert.threat_level}</Text>
                     </View>
                     <View style={styles.timestampRow}>
                        <Clock size={10} color={theme.colors.textMuted} />
                        <Text style={styles.timestampText}>
                           {new Date(alert.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </Text>
                     </View>
                  </View>

                  <Text style={styles.locationTitle} numberOfLines={1}>
                     {alert.location_name || 'NEURAL_NODE_CAM_01'}
                  </Text>

                  <View style={styles.alertFooter}>
                     <View style={styles.metaInfo}>
                        <Calendar size={10} color={theme.colors.textMuted} />
                        <Text style={styles.metaText}>{new Date(alert.created_at).toLocaleDateString()}</Text>
                     </View>
                     <ChevronRight size={16} color={theme.colors.surfaceHigh} />
                  </View>
               </View>
            </TouchableOpacity>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  header: {
    padding: 32,
    paddingTop: Platform.OS === 'ios' ? 60 : 40,
    backgroundColor: theme.colors.background,
  },
  title: {
    fontSize: 24,
    fontWeight: '900',
    color: theme.colors.textPrimary,
    letterSpacing: 2,
    fontFamily: Platform.OS === 'ios' ? 'Inter-Black' : 'sans-serif-black',
  },
  subtitle: {
    fontSize: 10,
    color: theme.colors.primary,
    fontWeight: '800',
    marginTop: 4,
    letterSpacing: 1.5,
    opacity: 0.8,
  },
  scrollContent: {
    padding: 24,
    paddingTop: 0,
    paddingBottom: 40,
  },
  statsSummary: {
    flexDirection: 'row',
    backgroundColor: theme.colors.surfaceLow,
    borderRadius: 16,
    padding: 20,
    marginBottom: 32,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
  },
  summaryItem: {
    flex: 1,
    alignItems: 'center',
  },
  summaryLabel: {
    fontSize: 8,
    fontWeight: '800',
    color: theme.colors.textMuted,
    letterSpacing: 1,
    marginBottom: 4,
  },
  summaryValue: {
    fontSize: 12,
    fontWeight: '900',
    color: theme.colors.textPrimary,
  },
  summaryDivider: {
    width: 1,
    height: '60%',
    backgroundColor: theme.colors.surfaceHigh,
    opacity: 0.3,
  },
  alertItem: {
    backgroundColor: theme.colors.surfaceLow,
    borderRadius: 16,
    marginBottom: 16,
    flexDirection: 'row',
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
  },
  threatStripe: {
    width: 6,
  },
  alertMain: {
    flex: 1,
    padding: 20,
  },
  alertHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  levelBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  levelText: {
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1,
  },
  timestampRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  timestampText: {
    fontSize: 11,
    fontWeight: '700',
    color: theme.colors.textMuted,
  },
  locationTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: theme.colors.textPrimary,
    marginBottom: 16,
  },
  alertFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: theme.colors.surfaceMedium,
    paddingTop: 12,
  },
  metaInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  metaText: {
    fontSize: 10,
    fontWeight: '700',
    color: theme.colors.textMuted,
  },
  empty: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 48,
    marginTop: 40,
  },
  emptyIconCircle: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: theme.colors.surfaceLow,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: '900',
    color: theme.colors.textPrimary,
    letterSpacing: 1.5,
    marginBottom: 12,
  },
  emptySub: {
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: 'center',
    lineHeight: 20,
    fontWeight: '600',
  },
});
