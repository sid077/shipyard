import { Text as RNText, StyleSheet, type StyleProp, type TextStyle } from 'react-native';

import { typeScale, useTheme, type TypeVariant } from '@/theme';

type Props = {
  children: React.ReactNode;
  variant?: TypeVariant;
  tone?: 'default' | 'muted' | 'primary' | 'danger' | 'onPrimary';
  align?: 'left' | 'center' | 'right';
  numberOfLines?: number;
  style?: StyleProp<TextStyle>;
  accessibilityRole?: 'header' | 'text' | 'link';
  testID?: string;
};

/**
 * All typography goes through here. A raw `<Text>` in product code means a size
 * that is not on the ramp, which is how an app stops looking like one app.
 */
export function Text({
  children,
  variant = 'body',
  tone = 'default',
  align = 'left',
  numberOfLines,
  style,
  accessibilityRole,
  testID,
}: Props) {
  const theme = useTheme();
  const step = typeScale[variant];
  const color = {
    default: theme.text,
    muted: theme.textMuted,
    primary: theme.primary,
    danger: theme.danger,
    onPrimary: theme.onPrimary,
  }[tone];

  return (
    <RNText
      testID={testID}
      numberOfLines={numberOfLines}
      accessibilityRole={accessibilityRole}
      style={[
        {
          color,
          fontSize: step.size,
          lineHeight: step.lineHeight,
          fontWeight: step.weight,
          letterSpacing: step.letterSpacing,
          textAlign: align,
        },
        style,
      ]}
    >
      {children}
    </RNText>
  );
}

export const textStyles = StyleSheet.create({});
