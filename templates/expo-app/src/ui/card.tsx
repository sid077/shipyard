import { View, type StyleProp, type ViewStyle } from 'react-native';

import { elevation, radii, spacing, useTheme } from '@/theme';

type Props = {
  children: React.ReactNode;
  variant?: 'flat' | 'raised';
  padded?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
};

export function Card({ children, variant = 'flat', padded = true, style, testID }: Props) {
  const theme = useTheme();
  return (
    <View
      testID={testID}
      style={[
        {
          backgroundColor: variant === 'raised' ? theme.surfaceRaised : theme.surface,
          borderColor: theme.border,
          borderWidth: variant === 'flat' ? 1 : 0,
          borderRadius: radii.lg,
          padding: padded ? spacing(4) : 0,
        },
        variant === 'raised' ? elevation(1) : undefined,
        style,
      ]}
    >
      {children}
    </View>
  );
}
