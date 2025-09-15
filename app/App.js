import { StatusBar } from 'expo-status-bar';
import React, { useState } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, Alert, Platform, ActivityIndicator, ScrollView, Dimensions } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

// Responsive spacing for small devices
const { width: DEVICE_WIDTH } = Dimensions.get('window');
const isSmallDevice = DEVICE_WIDTH < 400;
const spacing = {
  containerPH: isSmallDevice ? 16 : 24,
  containerPV: isSmallDevice ? 16 : 24,
  cardPH: isSmallDevice ? 16 : 24,
  cardPV: isSmallDevice ? 20 : 28,
  resultPH: isSmallDevice ? 14 : 18,
  resultPV: isSmallDevice ? 16 : 22,
  resultMaxH: isSmallDevice ? 420 : 520,
  resultScrollMaxH: isSmallDevice ? 370 : 470,
};

export default function App() {
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [summary, setSummary] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const getApiBase = () => {
    if (Platform.OS === 'web') {
      const host = (typeof window !== 'undefined' && window.location && window.location.hostname) ? window.location.hostname : 'localhost';
      return `http://${host}:8000`;
    }
    if (Platform.OS === 'android') {
      return 'http://10.0.2.2:8000'; // Android 에뮬레이터에서 localhost 매핑
    }
    return 'http://localhost:8000'; // iOS 시뮬레이터/기본
  };
  const API_BASE = getApiBase();

  const handleSummarizePress = async () => {
    setErrorMsg('');
    setSummary('');
    if (!youtubeUrl || youtubeUrl.length < 10) {
      const msg = '유효한 유튜브 링크를 입력해 주세요';
      if (Platform.OS === 'web') window.alert(msg); else Alert.alert('알림', msg);
      return;
    }

    try {
      setIsLoading(true);
      const res = await fetch(`${API_BASE}/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: youtubeUrl }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `서버 오류 (${res.status})`);
      }
      const data = await res.json();
      setSummary(data.summary || '요약 결과가 없습니다.');
    } catch (e) {
      setErrorMsg(e.message || '요청 중 오류가 발생했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopyPress = async () => {
    try {
      if (!summary) return;
      if (Platform.OS === 'web') {
        if (navigator && navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(summary);
          window.alert('복사되었습니다.');
          return;
        }
        const tmp = document.createElement('textarea');
        tmp.value = summary;
        document.body.appendChild(tmp);
        tmp.select();
        document.execCommand('copy');
        document.body.removeChild(tmp);
        window.alert('복사되었습니다.');
        return;
      }
      Alert.alert('알림', '모바일에서 복사하려면 expo-clipboard 설치가 필요합니다.');
    } catch (e) {
      if (Platform.OS === 'web') window.alert('복사에 실패했습니다.'); else Alert.alert('알림', '복사에 실패했습니다.');
    }
  };


  return (
    <LinearGradient
      colors={["#0B1437", "#14224A", "#1E2E66", "#2C3E8F"]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={styles.gradient}
    >
      <LinearGradient
        colors={["#5B7FFF33", "#B872FF22", "#00000000"]}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.accentBlob}
      />
      <View style={styles.container}>
        <View style={styles.card}>
          <Text style={styles.title}>유튜브 영상 요약</Text>
          <TextInput
            style={styles.input}
            placeholder="유튜브 링크를 입력하세요"
            placeholderTextColor="rgba(255,255,255,0.6)"
            value={youtubeUrl}
            onChangeText={setYoutubeUrl}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="done"
          />
          <View style={styles.buttonContainer}>
            <TouchableOpacity style={[styles.button, isLoading && { opacity: 0.8 }]} activeOpacity={0.85} onPress={isLoading ? undefined : handleSummarizePress}>
              {isLoading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.buttonText}>요약하기</Text>
              )}
            </TouchableOpacity>
          </View>

          {!!errorMsg && (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{errorMsg}</Text>
            </View>
          )}

          {!!summary && (
            <View style={styles.resultBox}>
              <Text style={styles.resultTitle}>요약 결과</Text>
              <ScrollView style={styles.resultScroll} contentContainerStyle={{ paddingBottom: 4 }}>
                <Text style={styles.resultText}>{summary}</Text>
              </ScrollView>
              <View style={styles.copyButtonContainerSmall}>
                <TouchableOpacity style={styles.copyButtonSmall} activeOpacity={0.85} onPress={handleCopyPress}>
                  <Text style={styles.copyButtonSmallText}>복사하기</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        </View>
        <StatusBar style="light" />
      </View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  gradient: {
    flex: 1,
  },
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.containerPH,
    paddingVertical: spacing.containerPV,
  },
  accentBlob: {
    position: 'absolute',
    width: 520,
    height: 520,
    borderRadius: 260,
    top: -140,
    right: -140,
    opacity: 0.7,
  },
  card: {
    width: '100%',
    maxWidth: 680,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderColor: 'rgba(255,255,255,0.18)',
    borderWidth: 1,
    borderRadius: 18,
    paddingHorizontal: spacing.cardPH,
    paddingVertical: spacing.cardPV,
    shadowColor: '#000',
    shadowOpacity: 0.25,
    shadowOffset: { width: 0, height: 10 },
    shadowRadius: 20,
    elevation: 8,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#FFFFFF',
    marginBottom: 20,
  },
  input: {
    width: '100%',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.22)',
    backgroundColor: 'rgba(10, 20, 50, 0.35)',
    borderRadius: 14,
    paddingHorizontal: 16,
    height: 48,
    marginBottom: 16,
    color: '#FFFFFF',
    fontSize: 16,
  },
  buttonContainer: {
    width: '100%',
  },
  button: {
    backgroundColor: '#6A7DFF',
    borderRadius: 14,
    height: 50,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#6A7DFF',
    shadowOpacity: 0.45,
    shadowOffset: { width: 0, height: 12 },
    shadowRadius: 16,
    elevation: 6,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '700',
  },
  errorBox: {
    marginTop: 14,
    backgroundColor: 'rgba(255, 99, 99, 0.12)',
    borderColor: 'rgba(255, 99, 99, 0.35)',
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  errorText: {
    color: '#FF9E9E',
  },
  resultBox: {
    marginTop: 26,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderColor: 'rgba(255,255,255,0.18)',
    borderWidth: 1,
    borderRadius: 14,
    paddingVertical: spacing.resultPV,
    paddingHorizontal: spacing.resultPH,
    maxHeight: spacing.resultMaxH,
  },
  resultTitle: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 10,
  },
  resultScroll: {
    maxHeight: spacing.resultScrollMaxH,
  },
  resultText: {
    color: '#E9ECFF',
    lineHeight: 24,
    fontSize: 16,
  },
  copyButtonContainerSmall: {
    marginTop: 10,
    alignItems: 'flex-end',
  },
  copyButtonSmall: {
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderColor: 'rgba(255,255,255,0.22)',
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copyButtonSmallText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '600',
  },
});
