import React, { useState } from 'react';
import { View, StyleSheet, TouchableOpacity, SafeAreaView, KeyboardAvoidingView, Platform } from 'react-native';
import { Text, TextInput, Button, HelperText } from 'react-native-paper';
import { useAuthStore } from '../store/authStore';
import { Shield, Fingerprint } from 'lucide-react-native';
import { theme } from '../styles/theme';

export default function LoginScreen({ navigation }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const { login, isLoading, error } = useAuthStore();

  const handleLogin = () => {
    login(email, password);
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView 
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <View style={styles.header}>
          <View style={styles.logoContainer}>
            <Shield size={40} color={theme.colors.primary} />
          </View>
          <Text style={styles.title}>SafeSphere</Text>
          <Text style={styles.subtitle}>Your Personal Safety Guardian</Text>
        </View>

        <View style={styles.form}>
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
              placeholderTextColor={theme.colors.textMuted}
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
              placeholderTextColor={theme.colors.textMuted}
            />
          </View>

          {error && (
            <HelperText type="error" visible={true} style={styles.error}>
              {error}
            </HelperText>
          )}

          <Button
            mode="contained"
            onPress={handleLogin}
            loading={isLoading}
            disabled={isLoading}
            style={styles.button}
            labelStyle={styles.buttonLabel}
          >
            Sign In
          </Button>

          <TouchableOpacity style={styles.biometricBtn}>
            <Fingerprint size={24} color={theme.colors.textMuted} />
            <Text style={styles.biometricText}>USE FINGERPRINT</Text>
          </TouchableOpacity>

          <TouchableOpacity 
            onPress={() => navigation.navigate('Register')}
            style={styles.link}
          >
            <Text style={styles.linkText}>
              Need an account? <Text style={styles.linkHighlight}>Register here</Text>
            </Text>
          </TouchableOpacity>
        </View>
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
    padding: 32,
    justifyContent: 'center',
  },
  header: {
    alignItems: 'center',
    marginBottom: 64,
  },
  logoContainer: {
    width: 80,
    height: 80,
    borderRadius: 24,
    backgroundColor: theme.colors.surfaceLow,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
    shadowColor: theme.colors.primary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.1,
    shadowRadius: 15,
  },
  title: {
    fontSize: 28,
    fontWeight: '900',
    color: theme.colors.textPrimary,
    letterSpacing: 4,
    fontFamily: Platform.OS === 'ios' ? 'Inter-Black' : 'sans-serif-black',
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
  biometricBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    marginTop: 24,
    opacity: 0.6,
  },
  biometricText: {
    color: theme.colors.textMuted,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1,
  },
  error: {
    color: theme.colors.error,
    fontWeight: '700',
    textAlign: 'center',
  },
  link: {
    marginTop: 48,
    alignItems: 'center',
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
