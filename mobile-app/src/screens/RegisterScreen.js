import React, { useState } from 'react';
import { View, StyleSheet, ScrollView, TouchableOpacity, SafeAreaView, KeyboardAvoidingView, Platform } from 'react-native';
import { Text, TextInput, Button, HelperText } from 'react-native-paper';
import { useAuthStore } from '../store/authStore';
import { ShieldCheck, UserPlus } from 'lucide-react-native';
import { theme } from '../styles/theme';

export default function RegisterScreen({ navigation }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const { register, isLoading, error } = useAuthStore();

  const handleRegister = () => {
    register(name, email, password, phone);
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView 
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
          <View style={styles.header}>
            <View style={styles.logoContainer}>
              <UserPlus size={40} color={theme.colors.primary} />
            </View>
            <Text style={styles.title}>Join Us</Text>
            <Text style={styles.subtitle}>Create your safety account</Text>
          </View>

          <View style={styles.form}>
            <View style={styles.inputWrapper}>
              <TextInput
                label="Your Name"
                value={name}
                onChangeText={setName}
                mode="flat"
                style={styles.input}
                textColor={theme.colors.textPrimary}
                underlineColor="transparent"
                activeUnderlineColor={theme.colors.primary}
              />
            </View>

            <View style={styles.inputWrapper}>
              <TextInput
                label="Email Address"
                value={email}
                onChangeText={setEmail}
                mode="flat"
                autoCapitalize="none"
                keyboardType="email-address"
                style={styles.input}
                textColor={theme.colors.textPrimary}
                underlineColor="transparent"
                activeUnderlineColor={theme.colors.primary}
              />
            </View>

            <View style={styles.inputWrapper}>
              <TextInput
                label="Phone Number"
                value={phone}
                onChangeText={setPhone}
                mode="flat"
                keyboardType="phone-pad"
                style={styles.input}
                textColor={theme.colors.textPrimary}
                underlineColor="transparent"
                activeUnderlineColor={theme.colors.primary}
              />
            </View>

            <View style={styles.inputWrapper}>
              <TextInput
                label="Password"
                value={password}
                onChangeText={setPassword}
                mode="flat"
                secureTextEntry
                style={styles.input}
                textColor={theme.colors.textPrimary}
                underlineColor="transparent"
                activeUnderlineColor={theme.colors.primary}
              />
            </View>

            {error && (
              <HelperText type="error" visible={true} style={styles.error}>
                {error}
              </HelperText>
            )}

            <Button
              mode="contained"
              onPress={handleRegister}
              loading={isLoading}
              disabled={isLoading}
              style={styles.button}
              labelStyle={styles.buttonLabel}
            >
              Create Account
            </Button>

            <TouchableOpacity 
              onPress={() => navigation.navigate('Login')}
              style={styles.link}
            >
              <Text style={styles.linkText}>
                Already have an account? <Text style={styles.linkHighlight}>Login instead</Text>
              </Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  keyboardView: {
    flex: 1,
  },
  scrollContent: {
    padding: 32,
    paddingTop: 64,
  },
  header: {
    alignItems: 'center',
    marginBottom: 48,
  },
  logoContainer: {
    width: 80,
    height: 80,
    borderRadius: 24,
    backgroundColor: theme.colors.surfaceLow,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: '900',
    color: theme.colors.textPrimary,
    letterSpacing: 4,
  },
  subtitle: {
    fontSize: 10,
    color: theme.colors.primary,
    fontWeight: '800',
    marginTop: 8,
    letterSpacing: 2,
    opacity: 0.8,
  },
  form: {
    width: '100%',
  },
  inputWrapper: {
    backgroundColor: theme.colors.surfaceLow,
    borderRadius: 12,
    marginBottom: 16,
    overflow: 'hidden',
  },
  input: {
    backgroundColor: 'transparent',
    height: 60,
    fontSize: 13,
    fontWeight: '700',
  },
  button: {
    marginTop: 16,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    height: 56,
    justifyContent: 'center',
  },
  buttonLabel: {
    fontWeight: '900',
    letterSpacing: 2,
    fontSize: 14,
    color: theme.colors.background,
  },
  error: {
    color: theme.colors.error,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 16,
  },
  link: {
    marginTop: 32,
    alignItems: 'center',
    marginBottom: 40,
  },
  linkText: {
    fontSize: 10,
    color: theme.colors.textMuted,
    fontWeight: '700',
    letterSpacing: 1,
  },
  linkHighlight: {
    color: theme.colors.primary,
    fontWeight: '900',
  },
});
