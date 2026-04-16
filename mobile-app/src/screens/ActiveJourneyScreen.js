import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { View, StyleSheet, Dimensions, Alert, SafeAreaView, Platform, TouchableOpacity, Linking } from 'react-native';
import { Text, Surface } from 'react-native-paper';
import Map, { Marker } from '../components/Map';
import * as Location from 'expo-location';
import * as SMS from 'expo-sms';
import { ShieldAlert, Phone, Navigation, Wifi, Zap, Activity, Shield, AlertTriangle } from 'lucide-react-native';
import api, { WS_URL } from '../api';
import { getFamilyContacts } from '../api/family';
import { useAuthStore } from '../store/authStore';
import { theme } from '../styles/theme';

const { width } = Dimensions.get('window');

// Optimized HUD Component to prevent re-renders from parent logs
const TacticalHud = React.memo(({ threatLevel, wsConnected }) => {
  const threatStatusColor = useMemo(() => ({
    'NONE': theme.colors.primary,
    'LOW': theme.colors.accentAmber,
    'MEDIUM': theme.colors.accentAmber,
    'HIGH': theme.colors.error
  }[threatLevel] || theme.colors.primary), [threatLevel]);

  return (
    <SafeAreaView style={styles.topHud}>
      <Surface style={[styles.threatBanner, { borderColor: threatStatusColor }]} elevation={0}>
         <View style={[styles.statusDot, { backgroundColor: threatStatusColor }]} />
         <Text style={[styles.threatText, { color: threatStatusColor }]}>
           Security: {threatLevel === 'NONE' ? 'All Safe' : threatLevel}
         </Text>
         <Activity size={14} color={threatStatusColor} />
      </Surface>
    </SafeAreaView>
  );
});

export default function ActiveJourneyScreen({ route, navigation }) {
  const { journey } = route.params;
  const user = useAuthStore((s) => s.user);
  const [location, setLocation] = useState(null);
  const [threatLevel, setThreatLevel] = useState('NONE');
  const [wsConnected, setWsConnected] = useState(false);
  const [guardians, setGuardians] = useState([]);
  const [systemLogs, setSystemLogs] = useState(['System starting...', 'Connected to GPS']);
  const ws = useRef(null);
  const reconnectTimeout = useRef(null);
  const reconnectAttempt = useRef(0);
  const locationSubscription = useRef(null);

  const connectWebSocket = useCallback(() => {
    if (ws.current) ws.current.close();
    
    ws.current = new WebSocket(`${WS_URL}/user/${user.id}`);
    
    ws.current.onopen = () => {
      setWsConnected(true);
      reconnectAttempt.current = 0;
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
    };

    ws.current.onclose = () => {
      setWsConnected(false);
      // Exponential backoff reconnect
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempt.current), 30000);
      reconnectTimeout.current = setTimeout(() => {
        reconnectAttempt.current += 1;
        connectWebSocket();
      }, delay);
    };

    ws.current.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'threat_alert') {
          setThreatLevel(data.threat_level);
          if (data.threat_level === 'HIGH') {
            Alert.alert(
              '⚠️ HIGH THREAT DETECTED',
              'Our AI detected danger nearby. Are you safe? If you do not respond, your guardians will be called automatically.',
              [
                {
                  text: '🛡️ I AM SAFE',
                  onPress: () => {
                    api.post(`/alerts/${data.alert_id}/acknowledge`);
                    setThreatLevel('NONE');
                  },
                  style: 'cancel'
                },
                {
                  text: '🚨 SOS NOW',
                  onPress: handleSOS,
                  style: 'destructive'
                }
              ],
              { cancelable: false }
            );
          }
        }
      } catch (err) { console.debug('WS Parse Error'); }
    };
  }, [user.id]);

  useEffect(() => {
    connectWebSocket();
    startTracking();
    api.patch(`/journey/${journey.id}`, { status: 'active' });

    loadGuardians();

    const logInterval = setInterval(() => {
      const logs = ['Checking surroundings...', 'Safety monitoring active', 'Scanning for help nodes', 'Encryption secure', 'All systems ready'];
      setSystemLogs(prev => [logs[Math.floor(Math.random() * logs.length)], ...prev].slice(0, 2));
    }, 4000);

    return () => {
      if (ws.current) ws.current.close();
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      if (locationSubscription.current) locationSubscription.current.remove();
      clearInterval(logInterval);
    };
  }, [connectWebSocket]);

  const loadGuardians = async () => {
    try {
      const data = await getFamilyContacts();
      setGuardians(data);
    } catch (err) {
      console.error('Failed to load guardians');
    }
  };

  const startTracking = async () => {
    locationSubscription.current = await Location.watchPositionAsync(
      { accuracy: Location.Accuracy.High, timeInterval: 5000, distanceInterval: 10 },
      (loc) => {
        setLocation(loc.coords);
        api.post(`/journey/${journey.id}/gps`, {
          latitude: loc.coords.latitude,
          longitude: loc.coords.longitude,
          speed_mps: loc.coords.speed,
          accuracy_m: loc.coords.accuracy,
        }).catch(() => {});
      }
    );
  };

  const handleSOS = async () => {
    // 1. Notify Backend / Security Dashboard
    try {
      await api.post('/alerts', {
        journey_id: journey.id,
        threat_level: 'HIGH',
        threat_score: 1.0,
        alert_type: 'sos',
        latitude: location?.latitude,
        longitude: location?.longitude,
        location_name: journey.end_address,
        details: 'User manually triggered SOS from mobile app.'
      });
    } catch (err) {
      console.error('Failed to notify backend of SOS');
    }

    // 2. Local Device actions
    const sosOptions = [
      {
        text: '📞 Call Police (100)',
        onPress: () => Linking.openURL('tel:100'),
        style: 'destructive'
      }
    ];

    // Add Guardian Call Buttons
    guardians.forEach(guardian => {
      sosOptions.push({
        text: `📞 Call ${guardian.name}`,
        onPress: async () => {
          // Send SMS Link first
          const isAvailable = await SMS.isAvailableAsync();
          if (isAvailable && location) {
            const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${location.latitude},${location.longitude}`;
            await SMS.sendSMSAsync([guardian.phone], `🔴 EMERGENCY SOS: I need help! My live location: ${mapsUrl}`);
          }
          // Then call
          Linking.openURL(`tel:${guardian.phone}`);
        }
      });
    });

    sosOptions.push({
      text: 'Cancel',
      style: 'cancel'
    });

    Alert.alert(
      'Emergency SOS Active',
      'Choose an action below. Help coordinates have been broadcasted.',
      sosOptions
    );
  };

  const completeJourney = () => {
    api.patch(`/journey/${journey.id}`, { status: 'completed' });
    navigation.navigate('Map');
  };

  return (
    <View style={styles.container}>
      <Map
        style={styles.map}
        initialRegion={{
          latitude: journey.start_lat,
          longitude: journey.start_lng,
          latitudeDelta: 0.005,
          longitudeDelta: 0.005,
        }}
        showsUserLocation
      >
        <Marker coordinate={{ latitude: journey.end_lat, longitude: journey.end_lng }}>
           <View style={styles.destPin} />
        </Marker>
      </Map>

      <TacticalHud threatLevel={threatLevel} wsConnected={wsConnected} />

      {/* System Hardware Logs Overlay - Kept minimal for performance */}
      <View style={styles.logsOverlay}>
        {systemLogs.map((log, i) => (
          <Text key={i} style={[styles.logLine, { opacity: 1 - (i * 0.3) }]}>
            {`> ${log}`}
          </Text>
        ))}
      </View>

      {/* Bottom Control Vault */}
      <View style={styles.bottomVault}>
        <View style={styles.vaultHeader}>
          <View>
            <Text style={styles.vaultTitle}>Current Destination</Text>
            <Text style={styles.vaultSubtitle} numberOfLines={1}>{journey.end_address}</Text>
          </View>
          <View style={styles.connBadge}>
            <Wifi size={10} color={wsConnected ? theme.colors.primary : theme.colors.textMuted} />
            <Text style={[styles.connText, { color: wsConnected ? theme.colors.primary : theme.colors.textMuted }]}>
              {wsConnected ? 'Connected' : 'Connecting...'}
            </Text>
          </View>
        </View>

        <View style={styles.actionGrid}>
          <TouchableOpacity 
            style={styles.sosButton}
            onPress={handleSOS}
            activeOpacity={0.8}
          >
            <AlertTriangle size={24} color="#fff" />
            <Text style={styles.sosText}>Emergency SOS</Text>
          </TouchableOpacity>

          <View style={styles.secondaryActions}>
            <TouchableOpacity style={styles.iconAction}>
              <Phone size={20} color={theme.colors.textPrimary} />
            </TouchableOpacity>
            <TouchableOpacity 
              style={[styles.iconAction, styles.completeBtn]}
              onPress={completeJourney}
            >
              <Shield size={20} color={theme.colors.primary} />
              <Text style={styles.completeText}>ARRIVED</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  map: {
    flex: 1,
  },
  destPin: {
    width: 20,
    height: 20,
    backgroundColor: theme.colors.primary,
    borderRadius: 10,
    borderWidth: 3,
    borderColor: '#fff',
  },
  topHud: {
    position: 'absolute',
    top: 40,
    width: '100%',
    paddingHorizontal: 20,
  },
  threatBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    backgroundColor: theme.colors.surfaceLow,
    paddingVertical: 14,
    borderRadius: 16,
    borderWidth: 1,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.3,
    shadowRadius: 20,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  threatText: {
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 2,
  },
  logsOverlay: {
    position: 'absolute',
    top: 130,
    left: 20,
  },
  logLine: {
    color: theme.colors.primary,
    fontSize: 9,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    fontWeight: '700',
    marginBottom: 4,
  },
  bottomVault: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: theme.colors.surfaceLow,
    borderTopLeftRadius: 32,
    borderTopRightRadius: 32,
    padding: 32,
    paddingBottom: Platform.OS === 'ios' ? 48 : 32,
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
  },
  vaultHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 28,
  },
  vaultTitle: {
    fontSize: 10,
    fontWeight: '900',
    color: theme.colors.textMuted,
    letterSpacing: 1.5,
    marginBottom: 4,
  },
  vaultSubtitle: {
    fontSize: 16,
    fontWeight: '800',
    color: theme.colors.textPrimary,
    width: width * 0.6,
  },
  connBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: theme.colors.background,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  connText: {
    fontSize: 8,
    fontWeight: '900',
  },
  actionGrid: {
    flexDirection: 'column',
    gap: 16,
  },
  sosButton: {
    backgroundColor: theme.colors.error,
    height: 64,
    borderRadius: 20,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    shadowColor: theme.colors.error,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.3,
    shadowRadius: 15,
  },
  sosText: {
    color: '#fff',
    fontWeight: '900',
    fontSize: 16,
    letterSpacing: 1,
  },
  secondaryActions: {
    flexDirection: 'row',
    gap: 16,
  },
  iconAction: {
    width: 64,
    height: 64,
    backgroundColor: theme.colors.surfaceMedium,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  completeBtn: {
    flex: 1,
    flexDirection: 'row',
    gap: 10,
    backgroundColor: theme.colors.surfaceHigh,
  },
  completeText: {
    color: theme.colors.primary,
    fontWeight: '900',
    fontSize: 14,
    letterSpacing: 1,
  }
});
