import React from 'react';
import { View, StyleSheet, ScrollView, TouchableOpacity, SafeAreaView, Platform, Alert, Linking } from 'react-native';
import { Text, Surface } from 'react-native-paper';
import { Phone, MapPin, ShieldAlert, Heart, Siren, Truck, Navigation, Share2 } from 'lucide-react-native';
import * as SMS from 'expo-sms';
import * as Location from 'expo-location';
import { theme } from '../styles/theme';
import { getFamilyContacts, addFamilyContact, deleteFamilyContact } from '../api/family';
import { useAuthStore } from '../store/authStore';
import { Plus, Trash2 } from 'lucide-react-native';

export default function EmergencyHubScreen({ navigation }) {
  const fetchGuardiansGlobally = useAuthStore((s) => s.fetchGuardians);

  const [guardians, setGuardians] = React.useState([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    loadGuardians();
  }, []);

  const loadGuardians = async () => {
    try {
      const data = await getFamilyContacts();
      setGuardians(data);
    } catch (err) {
      console.error('Failed to load guardians');
    } finally {
      setLoading(false);
    }
  };

  const handleAddGuardian = async () => {
    Alert.prompt(
      'Add Trusted Guardian',
      'Enter the phone number of someone you trust.',
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Next', 
          onPress: (phone) => {
            if (!phone) return;
            Alert.prompt(
              'Guardian Name',
              'What is their name?',
              [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Add',
                  onPress: async (name) => {
                    if (!name) return;
                    try {
                      await addFamilyContact({ name, phone, relationship_label: 'Guardian' });
                      await fetchGuardiansGlobally(); // Trigger global refresh
                      loadGuardians();
                    } catch (err) {
                      Alert.alert('Error', 'Could not add guardian');
                    }
                  }
                }
              ]
            );
          }
        }
      ],
      'plain-text'
    );
  };

  const handleDeleteGuardian = (id, name) => {
    Alert.alert(
      'Remove Guardian',
      `Are you sure you want to remove ${name}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Delete', 
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteFamilyContact(id);
              await fetchGuardiansGlobally(); // Trigger global refresh
              loadGuardians();
            } catch (err) {
              Alert.alert('Error', 'Could not delete');
            }
          }
        }
      ]
    );
  };

  const callEmergency = (number) => {
    Linking.openURL(`tel:${number}`);
  };

  const initiateGuardianEmergency = async (phone) => {
    // 1. Prepare SMS
    const isAvailable = await SMS.isAvailableAsync();
    let mapsUrl = "";
    
    try {
      let { status } = await Location.requestForegroundPermissionsAsync();
      if (status === 'granted') {
        const loc = await Location.getCurrentPositionAsync({});
        mapsUrl = `\nMy live location: https://www.google.com/maps/search/?api=1&query=${loc.coords.latitude},${loc.coords.longitude}`;
      }
    } catch (err) {
      console.debug('Location fetch failed for SMS');
    }

    if (isAvailable) {
      await SMS.sendSMSAsync(
        [phone],
        `🔴 EMERGENCY SOS: I need help!${mapsUrl}`
      );
    }
    
    // 2. Open Dialer
    Linking.openURL(`tel:${phone}`);
  };

  const shareLiveLocation = async () => {
    const isAvailable = await SMS.isAvailableAsync();
    if (isAvailable) {
      let { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') return;
      
      const loc = await Location.getCurrentPositionAsync({});
      const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${loc.coords.latitude},${loc.coords.longitude}`;
      
      const guardianPhones = guardians.map(g => g.phone).filter(p => !!p);
      
      await SMS.sendSMSAsync(
        guardianPhones,
        `🔴 EMERGENCY SOS: I need help! My live location: ${mapsUrl}`
      );
    } else {
      Alert.alert('Error', 'SMS services are not available on this device');
    }
  };

  const services = [
    { title: 'Police', number: '100', icon: Siren, color: '#3b82f6' },
    { title: 'Ambulance', number: '102', icon: Heart, color: '#ef4444' },
    { title: 'Fire Dept', number: '101', icon: Truck, color: '#f97316' },
    { title: 'Women Helpline', number: '1091', icon: ShieldAlert, color: theme.colors.primary },
  ];

  return (
    <View style={styles.container}>
      <SafeAreaView style={styles.header}>
        <View style={styles.headerTop}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Text style={styles.backBtn}>BACK</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Emergency Hub</Text>
          <View style={{ width: 40 }} />
        </View>
        <Text style={styles.subtitle}>Help is one tap away</Text>
      </SafeAreaView>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.grid}>
          {services.map((service) => (
            <TouchableOpacity 
              key={service.title} 
              style={styles.card}
              onPress={() => callEmergency(service.number)}
              activeOpacity={0.8}
            >
              <View style={[styles.iconCircle, { backgroundColor: service.color + '20' }]}>
                <service.icon size={32} color={service.color} />
              </View>
              <Text style={styles.cardTitle}>{service.title}</Text>
              <Text style={[styles.cardNum, { color: service.color }]}>{service.number}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <Surface style={styles.sosBanner} elevation={4}>
          <TouchableOpacity 
            style={styles.sosButton}
            onPress={shareLiveLocation}
          >
            <Share2 size={24} color="#fff" />
            <Text style={styles.sosBtnText}>Alert All Guardians</Text>
          </TouchableOpacity>
          <Text style={styles.sosDescription}>
            This will pre-fill a message with your GPS coordinates for all your saved trusted contacts.
          </Text>
        </Surface>

        {guardians.length > 0 && (
          <>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>YOUR TRUSTED GUARDIANS</Text>
              <TouchableOpacity onPress={handleAddGuardian}>
                 <Plus size={20} color={theme.colors.primary} />
              </TouchableOpacity>
            </View>
            <View style={styles.guardianList}>
              {guardians.map((guardian) => (
                <View key={guardian.id} style={styles.guardianCard}>
                  <TouchableOpacity 
                    style={styles.guardianInfo}
                    onPress={() => initiateGuardianEmergency(guardian.phone)}
                  >
                    <Text style={styles.guardianName}>{guardian.name}</Text>
                    <Text style={styles.guardianRelation}>{guardian.relationship_label}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity 
                    style={styles.deleteBtn}
                    onPress={() => handleDeleteGuardian(guardian.id, guardian.name)}
                  >
                    <Trash2 size={16} color={theme.colors.textMuted} />
                  </TouchableOpacity>
                  <TouchableOpacity 
                    style={styles.actionCircle}
                    onPress={() => initiateGuardianEmergency(guardian.phone)}
                  >
                    <Phone size={20} color="#fff" />
                  </TouchableOpacity>
                </View>
              ))}
            </View>
            <View style={{ marginBottom: 32 }} />
          </>
        )}

        {guardians.length === 0 && (
           <TouchableOpacity style={styles.emptyGuardians} onPress={handleAddGuardian}>
              <Plus size={24} color={theme.colors.primary} />
              <Text style={styles.emptyText}>Add your first trusted contact</Text>
           </TouchableOpacity>
        )}

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>NEARBY RESOURCES</Text>
        </View>

        <View style={styles.resourceList}>
          <View style={styles.resourceItem}>
            <MapPin size={20} color={theme.colors.textMuted} />
            <View style={styles.resourceInfo}>
              <Text style={styles.resourceName}>Main City Police Station</Text>
              <Text style={styles.resourceDist}>0.8 km away • Open 24/7</Text>
            </View>
            <TouchableOpacity onPress={() => callEmergency('100')}>
               <Phone size={20} color={theme.colors.primary} />
            </TouchableOpacity>
          </View>

          <View style={styles.resourceItem}>
            <MapPin size={20} color={theme.colors.textMuted} />
            <View style={styles.resourceInfo}>
              <Text style={styles.resourceName}>St. Mary's General Hospital</Text>
              <Text style={styles.resourceDist}>1.5 km away • Emergency ER</Text>
            </View>
             <TouchableOpacity onPress={() => callEmergency('102')}>
               <Phone size={20} color={theme.colors.primary} />
            </TouchableOpacity>
          </View>
        </View>
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
    padding: 24,
    backgroundColor: theme.colors.surfaceLow,
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  backBtn: {
    color: theme.colors.primary,
    fontWeight: '900',
    fontSize: 12,
  },
  title: {
    fontSize: 20,
    fontWeight: '900',
    color: theme.colors.textPrimary,
  },
  subtitle: {
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
  },
  content: {
    padding: 24,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
    marginBottom: 32,
  },
  card: {
    width: '47%',
    backgroundColor: theme.colors.surfaceLow,
    borderRadius: 24,
    padding: 20,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: theme.colors.textPrimary,
  },
  cardNum: {
    fontSize: 12,
    fontWeight: '900',
    marginTop: 4,
  },
  sosBanner: {
    backgroundColor: theme.colors.surfaceLow,
    borderRadius: 24,
    padding: 24,
    marginBottom: 32,
    borderWidth: 1,
    borderColor: theme.colors.primary + '40',
  },
  sosButton: {
    backgroundColor: theme.colors.primary,
    height: 56,
    borderRadius: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    marginBottom: 16,
  },
  sosBtnText: {
    color: theme.colors.background,
    fontWeight: '900',
    fontSize: 14,
  },
  sosDescription: {
    fontSize: 11,
    color: theme.colors.textMuted,
    textAlign: 'center',
    lineHeight: 16,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 10,
    fontWeight: '900',
    color: theme.colors.textMuted,
    letterSpacing: 2,
  },
  emptyGuardians: {
    backgroundColor: theme.colors.surfaceLow,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: theme.colors.primary,
    borderRadius: 20,
    padding: 32,
    alignItems: 'center',
    gap: 12,
    marginBottom: 32,
  },
  emptyText: {
    color: theme.colors.primary,
    fontWeight: '800',
    fontSize: 14,
  },
  resourceList: {
    gap: 12,
  },
  resourceItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceLow,
    padding: 16,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
    gap: 16,
  },
  resourceInfo: {
    flex: 1,
  },
  resourceName: {
    fontSize: 14,
    fontWeight: '800',
    color: theme.colors.textPrimary,
  },
  resourceDist: {
    fontSize: 11,
    color: theme.colors.textMuted,
    marginTop: 2,
  },
  guardianList: {
    gap: 12,
  },
  guardianCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceLow,
    padding: 16,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: theme.colors.primary + '30',
    gap: 16,
  },
  guardianInfo: {
    flex: 1,
  },
  guardianName: {
    fontSize: 16,
    fontWeight: '800',
    color: theme.colors.textPrimary,
  },
  guardianRelation: {
    fontSize: 12,
    color: theme.colors.primary,
    fontWeight: '700',
    textTransform: 'uppercase',
    marginTop: 2,
  },
  actionCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: theme.colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  deleteBtn: {
    padding: 8,
  },
});
