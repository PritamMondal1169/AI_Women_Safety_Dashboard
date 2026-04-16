import React, { memo } from 'react';
import MapView, { Marker, Polyline, PROVIDER_GOOGLE } from 'react-native-maps';

const Map = memo(({ children, ...props }) => {
  return (
    <MapView {...props}>
      {children}
    </MapView>
  );
});

export { Marker, Polyline, PROVIDER_GOOGLE };
export default Map;
