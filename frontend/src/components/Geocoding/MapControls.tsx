// src/components/Geocoding/MapControls.tsx
import React from 'react';

interface SliderControlProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step: number;
}

export const SliderControl: React.FC<SliderControlProps> = ({
  label,
  value,
  onChange,
  min,
  max,
  step
}) => {
  return (
    <div className="flex items-center space-x-2 mb-2">
      <label className="text-gray-200 w-24">{label}</label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1"
      />
      <input
        type="number"
        value={value}
        onChange={(e) => {
          const val = Number(e.target.value);
          if (val >= min && val <= max) {
            onChange(val);
          }
        }}
        className="w-20 px-2 py-1 bg-gray-700 text-gray-200 rounded"
      />
    </div>
  );
};

interface MapControlsProps {
  showSatellite: boolean;
  showStreetView: boolean;
  onShowSatelliteChange: (checked: boolean) => void;
  onShowStreetViewChange: (checked: boolean) => void;
  satelliteZoom: number;
  onSatelliteZoomChange: (value: number) => void;
  streetViewHeading: number;
  onStreetViewHeadingChange: (value: number) => void;
  streetViewPitch: number;
  onStreetViewPitchChange: (value: number) => void;
  streetViewFov: number;
  onStreetViewFovChange: (value: number) => void;
}

export const MapControls: React.FC<MapControlsProps> = ({
  showSatellite,
  showStreetView,
  onShowSatelliteChange,
  onShowStreetViewChange,
  satelliteZoom,
  onSatelliteZoomChange,
  streetViewHeading,
  onStreetViewHeadingChange,
  streetViewPitch,
  onStreetViewPitchChange,
  streetViewFov,
  onStreetViewFovChange,
}) => {
  return (
    <div className="p-4 bg-gray-800 rounded-lg mb-4">
      <div className="flex space-x-4 mb-4">
        <label className="flex items-center space-x-2 text-gray-200">
          <input
            type="checkbox"
            checked={showSatellite}
            onChange={(e) => onShowSatelliteChange(e.target.checked)}
            className="form-checkbox"
          />
          <span>衛星写真を表示</span>
        </label>
        <label className="flex items-center space-x-2 text-gray-200">
          <input
            type="checkbox"
            checked={showStreetView}
            onChange={(e) => onShowStreetViewChange(e.target.checked)}
            className="form-checkbox"
          />
          <span>ストリートビューを表示</span>
        </label>
      </div>

      {showSatellite && (
        <div className="mb-4">
          <h3 className="text-gray-200 font-bold mb-2">衛星写真設定</h3>
          <SliderControl
            label="ズームレベル"
            value={satelliteZoom}
            onChange={onSatelliteZoomChange}
            min={1}
            max={21}
            step={1}
          />
        </div>
      )}

      {showStreetView && (
        <div>
          <h3 className="text-gray-200 font-bold mb-2">ストリートビュー設定</h3>
          <SliderControl
            label="方角"
            value={streetViewHeading}
            onChange={onStreetViewHeadingChange}
            min={0}
            max={360}
            step={1}
          />
          <SliderControl
            label="上下角度"
            value={streetViewPitch}
            onChange={onStreetViewPitchChange}
            min={-90}
            max={90}
            step={1}
          />
          <SliderControl
            label="視野角"
            value={streetViewFov}
            onChange={onStreetViewFovChange}
            min={20}
            max={120}
            step={1}
          />
        </div>
      )}
    </div>
  );
};