import { useState } from 'react';
import { StyleSheet, TextInput, View, type KeyboardTypeOptions } from 'react-native';

import { MIN_TOUCH_TARGET, radii, spacing, typeScale, useTheme } from '@/theme';

import { Text } from './text';

type Props = {
  /** Always visible. A placeholder is not a label: it disappears on focus. */
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  error?: string;
  keyboardType?: KeyboardTypeOptions;
  autoFocus?: boolean;
  testID?: string;
};

export function Input({
  label,
  value,
  onChangeText,
  placeholder,
  error,
  keyboardType,
  autoFocus,
  testID,
}: Props) {
  const theme = useTheme();
  const [focused, setFocused] = useState(false);

  return (
    <View style={styles.wrapper}>
      <Text variant="caption" tone="muted">
        {label}
      </Text>
      <TextInput
        testID={testID}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={theme.textMuted}
        keyboardType={keyboardType}
        autoFocus={autoFocus}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        accessibilityLabel={label}
        // Error state must reach assistive tech, not only the eye.
        accessibilityState={{ disabled: false }}
        accessibilityHint={error}
        style={[
          styles.field,
          {
            color: theme.text,
            backgroundColor: theme.surface,
            borderColor: error ? theme.danger : focused ? theme.primary : theme.border,
            borderRadius: radii.md,
            fontSize: typeScale.body.size,
          },
        ]}
      />
      {error ? (
        <Text variant="caption" tone="danger">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { gap: 6 },
  field: {
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: spacing(4),
    paddingVertical: spacing(3),
    borderWidth: 1,
  },
});
