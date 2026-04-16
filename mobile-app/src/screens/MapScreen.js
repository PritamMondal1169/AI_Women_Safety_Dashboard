import React, { useState, useEffect } from 'react';
import { View, StyleSheet, Dimensions, TouchableOpacity, SafeAreaView, Platform } from 'react-native';
import { Text, TextInput, Button, IconButton } from 'react-native-paper';
import Map, { Marker, Polyline } from '../components/Map';
import * as Location from 'expo-location';
import { Navigation, Search, MapPin, Zap, ShieldCheck, ShieldAlert } from 'lucide-react-native';
import { theme } from '../styles/theme';
import { useAuthStore } from '../store/authStore';

const { width, height } = Dimensions.get('window');

export default function MapScreen({ navigation }) {
  const [location, setLocation] = useState(null);
  const [isPlanning, setIsPlanning] = useState(false);
  const [route, setRoute] = useState(null);
  const guardians = useAuthStore((s) => s.guardians);
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    (async () => {
      let { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') return;
      let loc = await Location.getCurrentPositionAsync({});
      setLocation(loc.coords);
    })();
  }, []);

  const handlePlanJourney = async () => {
    if (!destination) return;
    setIsPlanning(true);
    try {
      const destLat = location.latitude + 0.01;
      const destLng = location.longitude + 0.01;

      const response = await api.post('/journey', {
        start_lat: location.latitude,
        start_lng: location.longitude,
        start_address: 'CURRENT_LOC_ALPHA',
        end_lat: destLat,
        end_lng: destLng,
        end_address: destination,
      });

      setRoute(response.data);
    } catch (error) {
      console.error('Failed to plan journey:', error);
    } finally {
      setIsPlanning(false);
    }
  };

  const startJourney = () => {
    if (route) {
      navigation.navigate('ActiveJourney', { journey: route });
    }
  };

  return (
    <View style={styles.container}>
      <Map
        style={styles.map}
        initialRegion={{
          latitude: location?.latitude || 37.78825,
          longitude: location?.longitude || -122.4324,
          latitudeDelta: 0.01,
          longitudeDelta: 0.01,
        }}
        showsUserLocation
      >
        {route && (
          <Marker 
            coordinate={{ latitude: route.end_lat, longitude: route.end_lng }} 
            anchor={{ x: 0.5, y: 1 }}
          >
            <View style={styles.markerContainer}>
              <View style={styles.markerPin}>
                <MapPin size={18} color="#fff" />
              </View>
              <View style={styles.markerShadow} />
            </View>
          </Marker>
        )}
      </Map>

      {/* Top Search HUD */}
      <SafeAreaView style={styles.topHud}>
        <View style={styles.topHudContainer}>
          <View style={styles.searchBar}>
            <Search size={20} color={theme.colors.textMuted} style={styles.searchIcon} />
            <TextInput
              placeholder="Where are you going?"
              value={destination}
              onChangeText={setDestination}
              placeholderTextColor={theme.colors.textMuted}
              style={styles.searchInput}
              textColor={theme.colors.textPrimary}
              underlineColor="transparent"
              activeUnderlineColor="transparent"
              mode="flat"
            />
            <TouchableOpacity 
              onPress={handlePlanJourney}
              disabled={isPlanning}
              style={styles.planBtn}
            >
              <Navigation size={20} color={theme.colors.primary} />
            </TouchableOpacity>
          </View>
          
          <TouchableOpacity 
            style={styles.emergencyCircle}
            onPress={() => navigation.navigate('EmergencyHub')}
          >
            <ShieldAlert size={28} color="#fff" />
          </TouchableOpacity>
        </View>
      </SafeAreaView>

      {/* Bottom Tactical Info */}
      {route && (
        <View style={styles.bottomHud}>
          <View style={styles.routeHeader}>
            <View style={styles.badge}>
              <ShieldCheck size={12} color={theme.colors.primary} />
              <Text style={styles.badgeText}>Route is secure</Text>
            </View>
            <Text style={styles.destText}>{destination.toUpperCase()}</Text>
          </View>

          <View style={styles.statsGrid}>
            <View style={styles.statItem}>
              <Text style={styles.statLabel}>Distance</Text>
              <Text style={styles.statValue}>{(route.distance_m / 1000).toFixed(1)} km</Text>
            </View>
            <View style={styles.statDivider} />
            <View style={styles.statItem}>
              <Text style={styles.statLabel}>Travel Time</Text>
              <Text style={styles.statValue}>{Math.round(route.duration_s / 60)} mins</Text>
            </View>
            <View style={styles.statDivider} />
            <View style={styles.statItem}>
              <Text style={styles.statLabel}>Cameras Nearby</Text>
              <Text style={[styles.statValue, { color: theme.colors.primary }]}>12 Units</Text>
            </View>
          </View>

          <TouchableOpacity 
            style={styles.startButton}
            onPress={startJourney}
          >
            <Zap size={20} color={theme.colors.background} fill={theme.colors.background} />
            <Text style={styles.startBtnText}>Start Safe Journey</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Mandatory Guardian Lock Overlay */}
      {guardians.length === 0 && (
        <View style={styles.lockOverlay}>
          <Surface style={styles.lockCard} elevation={4}>
            <View style={styles.lockIconBox}>
                <ShieldAlert size={48} color="#ef4444" />
            </View>
            <Text style={styles.lockTitle}>Safety Setup Required</Text>
            <Text style={styles.lockBody}>
              SafeSphere requires at least one **Trusted Guardian** to be added before you can start a journey.
            </Text>
            <Text style={styles.lockBody}>
               This ensures someone can be notified instantly in case of an emergency.
            </Text>
            
            <TouchableOpacity 
              style={styles.lockButton}
              onPress={() => navigation.navigate('EmergencyHub')}
            >
              <Text style={styles.lockBtnText}>Add Trusted Guardian</Text>
            </TouchableOpacity>
          </Surface>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  map: {
    width: width,
    height: height,
  },
  topHud: {
    position: 'absolute',
    top: 40,
    width: '100%',
    paddingHorizontal: 20,
  },
  topHudContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  searchBar: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceLow,
    borderRadius: 16,
    paddingHorizontal: 16,
    height: 60,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.3,
    shadowRadius: 20,
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
  },
  emergencyCircle: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#ef4444',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#ef4444',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.4,
    shadowRadius: 20,
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.2)',
  },
  searchIcon: {
    marginRight: 12,
  },
  searchInput: {
    flex: 1,
    backgroundColor: 'transparent',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 1,
  },
  planBtn: {
    height: 40,
    width: 40,
    borderRadius: 12,
    backgroundColor: theme.colors.surfaceMedium,
    justifyContent: 'center',
    alignItems: 'center',
  },
  bottomHud: {
    position: 'absolute',
    bottom: 40,
    left: 20,
    right: 20,
    backgroundColor: theme.colors.surfaceLow,
    borderRadius: 24,
    padding: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 20 },
    shadowOpacity: 0.5,
    shadowRadius: 40,
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
  },
  routeHeader: {
    marginBottom: 20,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: theme.colors.background,
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 20,
    marginBottom: 12,
  },
  badgeText: {
    fontSize: 9,
    fontWeight: '900',
    color: theme.colors.primary,
    letterSpacing: 1,
  },
  destText: {
    fontSize: 22,
    fontWeight: '900',
    color: theme.colors.textPrimary,
    letterSpacing: -0.5,
  },
  statsGrid: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.background,
    borderRadius: 16,
    padding: 16,
    marginBottom: 20,
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statLabel: {
    fontSize: 8,
    fontWeight: '800',
    color: theme.colors.textMuted,
    letterSpacing: 1,
    marginBottom: 4,
  },
  statValue: {
    fontSize: 14,
    fontWeight: '900',
    color: theme.colors.textPrimary,
  },
  statDivider: {
    width: 1,
    height: '60%',
    backgroundColor: theme.colors.surfaceHigh,
    opacity: 0.5,
  },
  startButton: {
    backgroundColor: theme.colors.primary,
    height: 56,
    borderRadius: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  startBtnText: {
    color: theme.colors.background,
    fontWeight: '900',
    fontSize: 14,
    letterSpacing: 1,
  },
  markerContainer: {
    alignItems: 'center',
  },
  markerPin: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: theme.colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 3,
    borderColor: '#fff',
  },
  markerShadow: {
    width: 8,
    height: 4,
    backgroundColor: 'rgba(0,0,0,0.5)',
    borderRadius: 4,
    marginTop: 4,
  },
  lockOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(5, 10, 20, 0.9)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
    zIndex: 9999,
  },
  lockCard: {
    backgroundColor: theme.colors.surfaceLow,
    borderRadius: 32,
    padding: 32,
    alignItems: 'center',
    width: '100%',
    borderWidth: 1,
    borderColor: '#ef444450',
  },
  lockIconBox: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#ef444420',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  lockTitle: {
    fontSize: 22,
    fontWeight: '900',
    color: theme.colors.textPrimary,
    marginBottom: 16,
    textAlign: 'center',
  },
  lockBody: {
    fontSize: 14,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginBottom: 12,
    lineHeight: 20,
  },
  lockButton: {
    backgroundColor: theme.colors.primary,
    height: 56,
    borderRadius: 16,
    paddingHorizontal: 32,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 20,
    width: '100%',
  },
  lockBtnText: {
    color: theme.colors.background,
    fontWeight: '900',
    fontSize: 14,
    letterSpacing: 1,
  },
});
