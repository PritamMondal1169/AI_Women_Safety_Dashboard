import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

const Map = ({ children, style, initialRegion }) => {
  return (
    <View style={[style, styles.container]}>
      <View style={styles.content}>
        <Text style={styles.title}>SafeSphere Interactive Map</Text>
        <Text style={styles.subtitle}>Web Simulation Mode</Text>
        <Text style={styles.muted}>
          GPS: {initialRegion?.latitude.toFixed(4)}, {initialRegion?.longitude.toFixed(4)}
        </Text>
        <View style={styles.placeholder}>
            {/* Simulation of a map grid */}
            {[...Array(5)].map((_, i) => (
                <View key={i} style={styles.gridLine} />
            ))}
        </View>
        <View style={styles.children}>
            {children}
        </View>
      </View>
    </View>
  );
};

export const Marker = ({ coordinate, title }) => (
    <View style={styles.marker}>
        <Text style={styles.markerText}>📍 {title || 'Point'}</Text>
    </View>
);

export const Polyline = () => null;
export const PROVIDER_GOOGLE = 'google';

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#1e293b',
    justifyContent: 'center',
    alignItems: 'center',
  },
  content: {
    alignItems: 'center',
    padding: 20,
  },
  title: {
    color: '#fff',
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  subtitle: {
    color: '#6366f1',
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 12,
  },
  muted: {
    color: '#64748b',
    fontSize: 12,
    fontFamily: 'monospace',
  },
  placeholder: {
      width: 200,
      height: 120,
      marginTop: 24,
      borderRadius: 8,
      borderWidth: 1,
      borderColor: '#334155',
      backgroundColor: '#0f172a',
      overflow: 'hidden',
  },
  gridLine: {
      height: 1,
      backgroundColor: '#1e293b',
      marginTop: 20,
  },
  marker: {
      marginTop: 10,
      backgroundColor: '#334155',
      padding: 6,
      borderRadius: 4,
  },
  markerText: {
      color: '#fff',
      fontSize: 12,
  }
});

export default Map;
