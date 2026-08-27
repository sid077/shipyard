import { Pressable, StyleSheet, Text, type ViewStyle } from 'react-native';

import { radius, spacing, useTheme } from '@/theme';

type Props = {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary';
  disabled?: boolean;
  testID?: string;
  style?: ViewStyle;
};

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled = false,
  testID,
  style,
}: Props) {
  const theme = useTheme();
  const isPrimary = variant === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      testID={testID}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        {
          backgroundColor: isPrimary ? theme.primary : theme.surface,
          borderColor: isPrimary ? theme.primary : theme.border,
          opacity: disabled ? 0.4 : pressed ? 0.85 : 1,
        },
        style,
      ]}
    >
      <Text style={[styles.label, { color: isPrimary ? theme.onPrimary : theme.text }]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    // 44pt is the minimum comfortable touch target on both platforms.
    minHeight: 48,
    paddingHorizontal: spacing(5),
    paddingVertical: spacing(3),
    borderRadius: radius,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    fontSize: 16,
    fontWeight: '600',
  },
});
