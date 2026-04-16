import React from 'react';
import { View, StyleSheet, ScrollView, SafeAreaView, Platform, TouchableOpacity } from 'react-native';
import { Text, Avatar, Divider, Switch } from 'react-native-paper';
import { User, Shield, Bell, Lock, LogOut, ChevronRight, HelpCircle, HardDrive, Key, Fingerprint, Siren } from 'lucide-react-native';
import { useAuthStore } from '../store/authStore';
import { theme } from '../styles/theme';

export default function ProfileScreen() {
  const { user, logout } = useAuthStore();
  const [notifications, setNotifications] = React.useState(true);
  const [biometrics, setBiometrics] = React.useState(false);

  return (
    <View style={styles.container}>
      <SafeAreaView style={styles.header}>
        <View style={styles.avatarContainer}>
          <Avatar.Text 
            size={100} 
            label={user?.name?.[0]?.toUpperCase() || 'U'} 
            backgroundColor={theme.colors.surfaceLow} 
            labelStyle={styles.avatarLabel}
          />
          <View style={styles.onlineBadge} />
        </View>
        <Text style={styles.name}>{user?.name?.toUpperCase()}</Text>
        <Text style={styles.email}>{user?.email?.toLowerCase()}</Text>
        
        <TouchableOpacity style={styles.editButton} activeOpacity={0.7}>
          <Text style={styles.editButtonText}>Edit Profile</Text>
        </TouchableOpacity>
      </SafeAreaView>

      <ScrollView 
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>SETTINGS</Text>
          
          <View style={styles.settingItem}>
            <View style={styles.settingLabelGroup}>
               <View style={[styles.iconBox, { backgroundColor: theme.colors.primary + '15' }]}>
                  <Bell size={18} color={theme.colors.primary} />
               </View>
                <Text style={styles.settingLabel}>Alert Notifications</Text>
            </View>
            <Switch value={notifications} onValueChange={setNotifications} color={theme.colors.primary} />
          </View>

          <View style={styles.settingItem}>
            <View style={styles.settingLabelGroup}>
               <View style={[styles.iconBox, { backgroundColor: theme.colors.primary + '15' }]}>
                  <Fingerprint size={18} color={theme.colors.primary} />
               </View>
                <Text style={styles.settingLabel}>Use Fingerprint</Text>
            </View>
            <Switch value={biometrics} onValueChange={setBiometrics} color={theme.colors.primary} />
          </View>

          <TouchableOpacity 
            style={styles.settingItem} 
            activeOpacity={0.7}
            onPress={() => navigation.navigate('EmergencyHub')}
          >
            <View style={styles.settingLabelGroup}>
               <View style={[styles.iconBox, { backgroundColor: '#ef444420' }]}>
                  <Siren size={18} color="#ef4444" />
               </View>
                <Text style={styles.settingLabel}>Emergency Hub</Text>
            </View>
            <ChevronRight size={16} color={theme.colors.surfaceHigh} />
          </TouchableOpacity>

          <TouchableOpacity style={styles.settingItem} activeOpacity={0.7}>
            <View style={styles.settingLabelGroup}>
               <View style={[styles.iconBox, { backgroundColor: theme.colors.primary + '15' }]}>
                  <Key size={18} color={theme.colors.primary} />
               </View>
                <Text style={styles.settingLabel}>Privacy Key</Text>
            </View>
            <ChevronRight size={16} color={theme.colors.surfaceHigh} />
          </TouchableOpacity>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>INFORMATION</Text>
          
          <TouchableOpacity style={styles.settingItem} activeOpacity={0.7}>
            <View style={styles.settingLabelGroup}>
               <View style={[styles.iconBox, { backgroundColor: theme.colors.surfaceMedium }]}>
                  <HardDrive size={18} color={theme.colors.textMuted} />
               </View>
                <Text style={styles.settingLabel}>Data Privacy</Text>
            </View>
            <Text style={styles.versionText}>AES-256</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.settingItem} activeOpacity={0.7}>
            <View style={styles.settingLabelGroup}>
               <View style={[styles.iconBox, { backgroundColor: theme.colors.surfaceMedium }]}>
                  <HelpCircle size={18} color={theme.colors.textMuted} />
               </View>
                <Text style={styles.settingLabel}>Version 1.2.0 (Stable)</Text>
            </View>
            <ChevronRight size={16} color={theme.colors.surfaceHigh} />
          </TouchableOpacity>
        </View>

        <TouchableOpacity 
           style={styles.logoutButton} 
           onPress={logout}
           activeOpacity={0.8}
        >
          <LogOut size={20} color={theme.colors.error} />
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>
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
    paddingTop: Platform.OS === 'ios' ? 60 : 40,
    paddingBottom: 40,
    alignItems: 'center',
    backgroundColor: theme.colors.background,
  },
  avatarContainer: {
    position: 'relative',
    marginBottom: 20,
  },
  avatarLabel: {
    fontWeight: '900',
    color: theme.colors.primary,
  },
  onlineBadge: {
    position: 'absolute',
    bottom: 5,
    right: 5,
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: theme.colors.primary,
    borderWidth: 3,
    borderColor: theme.colors.background,
  },
  name: {
    color: theme.colors.textPrimary,
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: 1,
  },
  email: {
    color: theme.colors.primary,
    fontSize: 12,
    fontWeight: '800',
    marginTop: 6,
    letterSpacing: 0.5,
    opacity: 0.7,
  },
  editButton: {
    marginTop: 24,
    backgroundColor: theme.colors.surfaceLow,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
  },
  editButtonText: {
    color: theme.colors.textPrimary,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
  scroll: {
    padding: 24,
    paddingTop: 0,
    paddingBottom: 60,
  },
  section: {
    marginBottom: 32,
  },
  sectionTitle: {
    fontSize: 10,
    fontWeight: '900',
    color: theme.colors.textMuted,
    letterSpacing: 2,
    marginBottom: 20,
  },
  settingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: theme.colors.surfaceLow,
    padding: 16,
    borderRadius: 20,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
  },
  settingLabelGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  iconBox: {
    width: 40,
    height: 40,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  settingLabel: {
    fontSize: 12,
    fontWeight: '800',
    color: theme.colors.textPrimary,
    letterSpacing: 0.5,
  },
  versionText: {
    fontSize: 10,
    fontWeight: '900',
    color: theme.colors.primary,
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    backgroundColor: theme.colors.surfaceLow,
    padding: 20,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: theme.colors.error + '40',
    marginTop: 8,
  },
  logoutText: {
    color: theme.colors.error,
    fontWeight: '900',
    fontSize: 13,
    letterSpacing: 1.5,
  }
});
