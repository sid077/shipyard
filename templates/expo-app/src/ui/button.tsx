import { useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  StyleSheet,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { MIN_TOUCH_TARGET, radii, spacing, useTheme } from '@/theme';

import { haptics } from './haptics';
import { usePressScale } from './motion';
import { Text } from './text';

type Props = {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'md' | 'lg';
  disabled?: boolean;
  loading?: boolean;
  /** Fires a light haptic on press. Off by default; use it for real commits. */
  haptic?: boolean;
  accessibilityHint?: string;
  testID?: string;
  style?: StyleProp<ViewStyle>;
};

export function Button({
  label,
  onPress,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  haptic = false,
  accessibilityHint,
  testID,
  style,
}: Props) {
  const theme = useTheme();
  const [pressed, setPressed] = useState(false);
  const { scale, onPressIn, onPressOut } = usePressScale();
  const inactive = disabled || loading;

  const background = {
    primary: pressed ? theme.primaryPressed : theme.primary,
    secondary: theme.surface,
    ghost: 'transparent',
    danger: theme.danger,
  }[variant];
  const foreground = {
    primary: 'onPrimary',
    secondary: 'default',
    ghost: 'primary',
    danger: 'onPrimary',
  }[variant] as 'onPrimary' | 'default' | 'primary';
  const border = variant === 'secondary' ? theme.border : 'transparent';

  return (
    <Animated.View style={[{ transform: [{ scale }] }, style]}>
      <Pressable
        testID={testID}
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityHint={accessibilityHint}
        // A disabled control that does not announce itself is a trap.
        accessibilityState={{ disabled: inactive, busy: loading }}
        disabled={inactive}
        onPress={() => {
          if (haptic) void haptics.tap();
          onPress();
        }}
        onPressIn={() => {
          setPressed(true);
          onPressIn();
        }}
        onPressOut={() => {
          setPressed(false);
          onPressOut();
        }}
        style={[
          styles.base,
          {
            minHeight: size === 'lg' ? MIN_TOUCH_TARGET + 8 : MIN_TOUCH_TARGET,
            paddingHorizontal: spacing(size === 'lg' ? 6 : 5),
            backgroundColor: background,
            borderColor: border,
            borderRadius: radii.md,
            opacity: inactive ? 0.45 : 1,
          },
        ]}
      >
        {loading ? (
          <ActivityIndicator
            color={variant === 'secondary' || variant === 'ghost' ? theme.text : theme.onPrimary}
          />
        ) : (
          <Text variant="bodyStrong" tone={foreground}>
            {label}
          </Text>
        )}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
  },
});
