import { useEffect, useState } from 'react';
import { ActivityIndicator, Animated, StyleSheet, View } from 'react-native';

import { motion, radii, spacing, useTheme } from '@/theme';

import { useReducedMotion } from './motion';
import { Text } from './text';

/**
 * A loading placeholder shaped like the content that is coming.
 *
 * Skeletons beat spinners when the shape is known: the layout does not jump
 * when the data lands.
 */
export function Skeleton({
  variant = 'row',
  testID,
}: {
  variant?: 'row' | 'block' | 'line';
  testID?: string;
}) {
  const theme = useTheme();
  const reduced = useReducedMotion();
  const [shimmer] = useState(() => new Animated.Value(0.4));

  useEffect(() => {
    if (reduced) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(shimmer, { toValue: 0.9, duration: 700, useNativeDriver: true }),
        Animated.timing(shimmer, { toValue: 0.4, duration: 700, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [shimmer, reduced]);

  const height = { row: 64, block: 120, line: 16 }[variant];

  return (
    <Animated.View
      testID={testID}
      accessibilityRole="progressbar"
      accessibilityLabel="Loading"
      style={{
        height,
        opacity: reduced ? 0.5 : shimmer,
        backgroundColor: theme.border,
        borderRadius: radii.sm,
        marginBottom: spacing(2),
      }}
    />
  );
}

export function Spinner({ label, testID }: { label?: string; testID?: string }) {
  const theme = useTheme();
  return (
    <View testID={testID} style={styles.spinner} accessibilityRole="progressbar">
      <ActivityIndicator color={theme.primary} />
      {label ? (
        <Text variant="caption" tone="muted">
          {label}
        </Text>
      ) : null}
    </View>
  );
}

export function Badge({
  label,
  tone = 'neutral',
  testID,
}: {
  label: string;
  tone?: 'neutral' | 'primary' | 'success' | 'danger';
  testID?: string;
}) {
  const theme = useTheme();
  const background = {
    neutral: theme.surface,
    primary: theme.primary,
    success: theme.success,
    danger: theme.danger,
  }[tone];
  const foreground = tone === 'neutral' ? 'muted' : 'onPrimary';

  return (
    <View
      testID={testID}
      style={[styles.badge, { backgroundColor: background, borderRadius: radii.full }]}
    >
      <Text variant="caption" tone={foreground}>
        {label}
      </Text>
    </View>
  );
}

export function Divider() {
  const theme = useTheme();
  return <View style={[styles.divider, { backgroundColor: theme.border }]} />;
}

const styles = StyleSheet.create({
  spinner: { alignItems: 'center', gap: spacing(2), paddingVertical: spacing(6) },
  badge: { paddingHorizontal: spacing(2), paddingVertical: spacing(1), alignSelf: 'flex-start' },
  divider: { height: StyleSheet.hairlineWidth, width: '100%' },
});

export { motion };
