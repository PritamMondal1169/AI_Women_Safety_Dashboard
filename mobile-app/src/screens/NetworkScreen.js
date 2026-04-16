import React, { useState, useEffect } from 'react';
import { View, StyleSheet, ScrollView, RefreshControl, SafeAreaView, Platform, TouchableOpacity } from 'react-native';
import { Text, Button, Avatar, Portal, Modal, TextInput, IconButton } from 'react-native-paper';
import { Users, UserPlus, Phone, Mail, Shield, Plus, ShieldCheck, UserCheck } from 'lucide-react-native';
import api from '../api';
import { theme } from '../styles/theme';

export default function NetworkScreen() {
  const [contacts, setContacts] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [relationship, setRelationship] = useState('');

  const loadContacts = async () => {
    try {
      const response = await api.get('/auth/family');
      setContacts(response.data);
    } catch (error) {
      console.error('Failed to load contacts:', error);
    }
  };

  useEffect(() => {
    loadContacts();
  }, []);

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true);
    await loadContacts();
    setRefreshing(false);
  }, []);

  const handleAddContact = async () => {
    try {
      await api.post('/auth/family', {
        name,
        phone,
        email,
        relationship_label: relationship,
      });
      loadContacts();
      setModalVisible(false);
      setName(''); setPhone(''); setEmail(''); setRelationship('');
    } catch (error) {
      console.error('Failed to add contact:', error);
    }
  };

  return (
    <View style={styles.container}>
      <SafeAreaView style={styles.header}>
        <Text style={styles.title}>GUARDIAN NETWORK</Text>
        <Text style={styles.subtitle}>SYNKED SAFETY NODES // {contacts.length} ACTIVE</Text>
      </SafeAreaView>

      <ScrollView 
        contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={theme.colors.primary} />}
        showsVerticalScrollIndicator={false}
      >
        {contacts.length === 0 ? (
          <View style={styles.empty}>
            <View style={styles.emptyIconCircle}>
               <Users size={48} color={theme.colors.primary} />
            </View>
            <Text style={styles.emptyTitle}>NO GUARDIANS LINKED</Text>
            <Text style={styles.emptySub}>Add trusted entities to your safety mesh for instant emergency broadcasting.</Text>
            <TouchableOpacity 
               style={styles.emptyButton} 
               onPress={() => setModalVisible(true)}
            >
               <Plus size={20} color={theme.colors.background} />
               <Text style={styles.emptyButtonText}>INITIATE PROVISIONING</Text>
            </TouchableOpacity>
          </View>
        ) : (
          contacts.map(contact => (
            <View key={contact.id} style={styles.guardianCard}>
               <View style={styles.cardMain}>
                  <Avatar.Text 
                    size={56} 
                    label={contact.name[0].toUpperCase()} 
                    backgroundColor={theme.colors.surfaceHigh} 
                    labelStyle={styles.avatarLabel}
                  />
                  <View style={styles.info}>
                     <View style={styles.nameRow}>
                        <Text style={styles.guardianName}>{contact.name.toUpperCase()}</Text>
                        <UserCheck size={14} color={theme.colors.primary} />
                     </View>
                     <Text style={styles.relationshipLabel}>{contact.relationship_label.toUpperCase()}</Text>
                     
                     <View style={styles.telemRow}>
                        <View style={styles.telemItem}>
                           <Phone size={10} color={theme.colors.textMuted} />
                           <Text style={styles.telemText}>{contact.phone}</Text>
                        </View>
                        {contact.email && (
                           <>
                              <View style={styles.telemDivider} />
                              <View style={styles.telemItem}>
                                 <Mail size={10} color={theme.colors.textMuted} />
                                 <Text style={styles.telemText} numberOfLines={1}>{contact.email}</Text>
                              </View>
                           </>
                        )}
                     </View>
                  </View>
               </View>
               <TouchableOpacity style={styles.moreOptions}>
                  <ShieldCheck size={18} color={theme.colors.surfaceHigh} />
               </TouchableOpacity>
            </View>
          ))
        )}
      </ScrollView>

      <TouchableOpacity 
         style={styles.fab} 
         onPress={() => setModalVisible(true)}
         activeOpacity={0.8}
      >
         <Plus size={28} color={theme.colors.background} />
      </TouchableOpacity>

      <Portal>
        <Modal 
          visible={modalVisible} 
          onDismiss={() => setModalVisible(false)} 
          contentContainerStyle={styles.modal}
        >
          <Text style={styles.modalTitle}>NEW GUARDIAN PROTOCOL</Text>
          
          <View style={styles.inputGroup}>
            <TextInput 
              label="PROTOCOL NAME" 
              value={name} 
              onChangeText={setName} 
              mode="flat" 
              style={styles.modalInput}
              textColor={theme.colors.textPrimary}
              underlineColor="transparent"
              activeUnderlineColor={theme.colors.primary}
            />
          </View>

          <View style={styles.inputGroup}>
            <TextInput 
              label="TELEMETRY_LINK (PHONE)" 
              value={phone} 
              onChangeText={setPhone} 
              mode="flat" 
              keyboardType="phone-pad"
              style={styles.modalInput} 
              textColor={theme.colors.textPrimary}
              underlineColor="transparent"
              activeUnderlineColor={theme.colors.primary}
            />
          </View>

          <View style={styles.inputGroup}>
            <TextInput 
              label="SIGNAL_ADDR (EMAIL)" 
              value={email} 
              onChangeText={setEmail} 
              mode="flat" 
              keyboardType="email-address"
              style={styles.modalInput} 
              textColor={theme.colors.textPrimary}
              underlineColor="transparent"
              activeUnderlineColor={theme.colors.primary}
            />
          </View>

          <View style={styles.inputGroup}>
            <TextInput 
              label="RELATIONSHIP_TAG" 
              value={relationship} 
              onChangeText={setRelationship} 
              mode="flat" 
              style={styles.modalInput} 
              textColor={theme.colors.textPrimary}
              underlineColor="transparent"
              activeUnderlineColor={theme.colors.primary}
            />
          </View>

          <TouchableOpacity style={styles.modalAddBtn} onPress={handleAddContact}>
            <Shield size={20} color={theme.colors.background} />
            <Text style={styles.modalAddBtnText}>AUTHORIZE GUARDIAN</Text>
          </TouchableOpacity>
        </Modal>
      </Portal>
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
    paddingBottom: 120,
  },
  guardianCard: {
    backgroundColor: theme.colors.surfaceLow,
    borderRadius: 24,
    marginBottom: 16,
    flexDirection: 'row',
    alignItems: 'center',
    padding: 20,
    borderWidth: 1,
    borderColor: theme.colors.surfaceMedium,
  },
  cardMain: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 20,
  },
  avatarLabel: {
    fontWeight: '900',
    color: theme.colors.primary,
  },
  info: {
    flex: 1,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 2,
  },
  guardianName: {
    fontSize: 16,
    fontWeight: '900',
    color: theme.colors.textPrimary,
    letterSpacing: 0.5,
  },
  relationshipLabel: {
    fontSize: 9,
    fontWeight: '800',
    color: theme.colors.primary,
    letterSpacing: 1,
    marginBottom: 12,
  },
  telemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  telemItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  telemText: {
    fontSize: 11,
    fontWeight: '700',
    color: theme.colors.textMuted,
  },
  telemDivider: {
    width: 1,
    height: 10,
    backgroundColor: theme.colors.surfaceHigh,
    opacity: 0.3,
  },
  moreOptions: {
    width: 40,
    height: 40,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  fab: {
    position: 'absolute',
    bottom: 40,
    right: 32,
    backgroundColor: theme.colors.primary,
    width: 64,
    height: 64,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: theme.colors.primary,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.3,
    shadowRadius: 20,
    elevation: 8,
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
    marginBottom: 32,
  },
  emptyButton: {
    backgroundColor: theme.colors.primary,
    height: 56,
    paddingHorizontal: 24,
    borderRadius: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  emptyButtonText: {
    color: theme.colors.background,
    fontWeight: '900',
    fontSize: 13,
    letterSpacing: 1,
  },
  modal: {
    backgroundColor: theme.colors.surfaceLow,
    padding: 32,
    margin: 24,
    borderRadius: 24,
    borderColor: theme.colors.surfaceMedium,
    borderWidth: 1,
  },
  modalTitle: {
    fontSize: 16,
    fontWeight: '900',
    color: theme.colors.textPrimary,
    letterSpacing: 2,
    marginBottom: 24,
    textAlign: 'center',
  },
  inputGroup: {
    backgroundColor: theme.colors.background,
    borderRadius: 12,
    marginBottom: 16,
    overflow: 'hidden',
  },
  modalInput: {
    backgroundColor: 'transparent',
    height: 60,
    fontSize: 12,
    fontWeight: '700',
  },
  modalAddBtn: {
    backgroundColor: theme.colors.primary,
    height: 60,
    borderRadius: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    marginTop: 16,
  },
  modalAddBtnText: {
    color: theme.colors.background,
    fontWeight: '900',
    fontSize: 14,
    letterSpacing: 1,
  }
});
