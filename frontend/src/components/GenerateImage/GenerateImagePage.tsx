// frontend/src/components/GenerateImage/GenerateImagePage.tsx
import React, { useState, useEffect } from "react";
import { useToken } from "../../hooks/useToken";
import * as Config from "../../config";
import generateId from "../../utils/idGenerator";

interface ImageGenerationParams {
  prompt: string;
  model_name: string;
  negative_prompt: string;
  number_of_images: number;
  seed: string | null;
  aspect_ratio: string;
  language: string;
  add_watermark: boolean;
  safety_filter_level: string;
  person_generation: string;
}

const GenerateImagePage: React.FC = () => {

  const token = useToken();
  const API_BASE_URL: string = Config.API_BASE_URL;
  const serverConfig = Config.getServerConfig();

  // 状態変数
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [generatedImages, setGeneratedImages] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [enlargedImage, setEnlargedImage] = useState<string | null>(null);

  // フォーム状態
  const [params, setParams] = useState<ImageGenerationParams>({
    prompt: "",
    model_name: "",
    negative_prompt: "",
    number_of_images: 1,
    seed: null,
    aspect_ratio: "1:1",
    language: "auto",
    add_watermark: false,
    safety_filter_level: "block_medium_and_above",
    person_generation: "allow_adult",
  });

  // 選択肢のオプション
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [aspectRatioOptions, setAspectRatioOptions] = useState<string[]>([]);
  const [numberOfImagesOptions, setNumberOfImagesOptions] = useState<number[]>([]);
  const [languageOptions, setLanguageOptions] = useState<string[]>([]);
  const [safetyFilterOptions, setSafetyFilterOptions] = useState<string[]>([]);
  const [personGenerationOptions, setPersonGenerationOptions] = useState<string[]>([]);

  // 設定の読み込み
  useEffect(() => {
    // サーバー設定がある場合のみ処理する
    if (serverConfig) {
      // モデルオプション
      if (serverConfig.IMAGEN_MODELS) {
        try {
          const { options, defaultOption } = Config.parseOptionsWithDefault(serverConfig.IMAGEN_MODELS);
          if (options.length > 0) {
            setModelOptions(options);
            setParams(prev => ({ ...prev, model_name: defaultOption }));
          }
        } catch (err) {
          console.error("モデルオプションの解析エラー:", err);
        }
      }

      // アスペクト比オプション
      if (serverConfig.IMAGEN_ASPECT_RATIOS) {
        try {
          const { options, defaultOption } = Config.parseOptionsWithDefault(serverConfig.IMAGEN_ASPECT_RATIOS);
          if (options.length > 0) {
            setAspectRatioOptions(options);
            setParams(prev => ({ ...prev, aspect_ratio: defaultOption }));
          }
        } catch (err) {
          console.error("アスペクト比オプションの解析エラー:", err);
        }
      }

      // 画像数オプション
      if (serverConfig.IMAGEN_NUMBER_OF_IMAGES) {
        try {
          const { options, defaultOption } = Config.parseNumberOptionsWithDefault(serverConfig.IMAGEN_NUMBER_OF_IMAGES);
          if (options.length > 0) {
            setNumberOfImagesOptions(options);
            setParams(prev => ({ ...prev, number_of_images: defaultOption }));
          }
        } catch (err) {
          console.error("画像数オプションの解析エラー:", err);
        }
      }

      // 言語オプション
      if (serverConfig.IMAGEN_LANGUAGES) {
        try {
          const { options, defaultOption } = Config.parseOptionsWithDefault(serverConfig.IMAGEN_LANGUAGES);
          if (options.length > 0) {
            setLanguageOptions(options);
            setParams(prev => ({ ...prev, language: defaultOption }));
          }
        } catch (err) {
          console.error("言語オプションの解析エラー:", err);
        }
      }

      // セーフティフィルターオプション
      if (serverConfig.IMAGEN_SAFETY_FILTER_LEVELS) {
        try {
          const { options, defaultOption } = Config.parseOptionsWithDefault(serverConfig.IMAGEN_SAFETY_FILTER_LEVELS);
          if (options.length > 0) {
            setSafetyFilterOptions(options);
            setParams(prev => ({ ...prev, safety_filter_level: defaultOption }));
          }
        } catch (err) {
          console.error("セーフティフィルターオプションの解析エラー:", err);
        }
      }

      // 人物生成オプション
      if (serverConfig.IMAGEN_PERSON_GENERATIONS) {
        try {
          const { options, defaultOption } = Config.parseOptionsWithDefault(serverConfig.IMAGEN_PERSON_GENERATIONS);
          if (options.length > 0) {
            setPersonGenerationOptions(options);
            setParams(prev => ({ ...prev, person_generation: defaultOption }));
          }
        } catch (err) {
          console.error("人物生成オプションの解析エラー:", err);
        }
      }
    }
  }, [serverConfig]);

  // フォーム変更ハンドラー
  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setParams((prev) => ({ ...prev, [name]: value }));
  };

  // チェックボックス変更ハンドラー
  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, checked } = e.target;
    setParams((prev) => ({ ...prev, [name]: checked }));
  };

  // 画像生成実行
  const generateImage = async () => {
    if (!params.prompt) {
      setError("プロンプトを入力してください");
      return;
    }

    setError(null);
    setIsGenerating(true);

    try {
      // リクエストペイロードの作成
      const payload = {
        prompt: params.prompt,
        model_name: params.model_name,
        negative_prompt: params.negative_prompt || "",
        number_of_images: params.number_of_images,
        seed: params.seed && params.seed.trim() !== "" ? parseInt(params.seed) : null,
        aspect_ratio: params.aspect_ratio,
        language: params.language,
        add_watermark: params.add_watermark,
        safety_filter_level: params.safety_filter_level,
        person_generation: params.person_generation,
      };
      const response = await fetch(`${API_BASE_URL}/backend/generate-image`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          "X-Request-Id": generateId(), // リクエストIDを追加
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "画像生成に失敗しました");
      }

      const data = await response.json();

      if (data.images && Array.isArray(data.images)) {
        setGeneratedImages(data.images);
      } else {
        throw new Error("画像データが無効です");
      }
    } catch (err) {
      console.error("画像生成エラー:", err);
      setError(err instanceof Error ? err.message : "画像生成中にエラーが発生しました");
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="p-4 bg-dark-primary min-h-[calc(100vh-64px)]">
      <h1 className="text-3xl font-bold mb-6 text-gray-100">画像生成</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* 設定パネル */}
        <div className="md:col-span-1 bg-gray-800 rounded-lg p-6 shadow-lg">
          <h2 className="text-xl font-bold mb-4 text-gray-100">生成設定</h2>

          {/* プロンプト入力 */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              プロンプト (必須)
            </label>
            <textarea
              name="prompt"
              value={params.prompt}
              onChange={handleInputChange}
              className="w-full p-2 bg-gray-700 border border-gray-600 rounded-md text-gray-100"
              rows={5}
              placeholder="生成したい画像の詳細な説明を入力してください"
            />
          </div>

          {/* ネガティブプロンプト */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              ネガティブプロンプト (省略可)
            </label>
            <textarea
              name="negative_prompt"
              value={params.negative_prompt}
              onChange={handleInputChange}
              className="w-full p-2 bg-gray-700 border border-gray-600 rounded-md text-gray-100"
              rows={3}
              placeholder="生成したくない要素を入力してください"
            />
          </div>

          {/* シード */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              シード (省略可)
            </label>
            <input
              type="text"
              name="seed"
              value={params.seed || ""}
              onChange={handleInputChange}
              className="w-full p-2 bg-gray-700 border border-gray-600 rounded-md text-gray-100"
              placeholder="空欄の場合はランダム"
            />
            <p className="text-xs text-gray-400 mt-1">
              同じシード値を使用することで、類似した画像を生成できます
            </p>
          </div>

          {/* モデル選択 */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              モデル
            </label>
            <select
              name="model_name"
              value={params.model_name}
              onChange={handleInputChange}
              className="w-full p-2 bg-gray-700 border border-gray-600 rounded-md text-gray-100"
            >
              {modelOptions.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </div>

          {/* 画像数選択 */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              生成枚数
            </label>
            <select
              name="number_of_images"
              value={params.number_of_images}
              onChange={handleInputChange}
              className="w-full p-2 bg-gray-700 border border-gray-600 rounded-md text-gray-100"
            >
              {numberOfImagesOptions.map((num) => (
                <option key={num} value={num}>
                  {num}枚
                </option>
              ))}
            </select>
          </div>

          {/* アスペクト比選択 */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              アスペクト比
            </label>
            <select
              name="aspect_ratio"
              value={params.aspect_ratio}
              onChange={handleInputChange}
              className="w-full p-2 bg-gray-700 border border-gray-600 rounded-md text-gray-100"
            >
              {aspectRatioOptions.map((ratio) => (
                <option key={ratio} value={ratio}>
                  {ratio}
                </option>
              ))}
            </select>
          </div>

          {/* 言語選択 */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              言語
            </label>
            <select
              name="language"
              value={params.language}
              onChange={handleInputChange}
              className="w-full p-2 bg-gray-700 border border-gray-600 rounded-md text-gray-100"
            >
              {languageOptions.map((lang) => (
                <option key={lang} value={lang}>
                  {lang}
                </option>
              ))}
            </select>
          </div>

          {/* セーフティフィルター */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              セーフティフィルター
            </label>
            <select
              name="safety_filter_level"
              value={params.safety_filter_level}
              onChange={handleInputChange}
              className="w-full p-2 bg-gray-700 border border-gray-600 rounded-md text-gray-100"
            >
              {safetyFilterOptions.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
          </div>

          {/* 人物生成 */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              人物生成設定
            </label>
            <select
              name="person_generation"
              value={params.person_generation}
              onChange={handleInputChange}
              className="w-full p-2 bg-gray-700 border border-gray-600 rounded-md text-gray-100"
            >
              {personGenerationOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>

          {/* ウォーターマーク */}
          <div className="mb-6">
            <label className="flex items-center">
              <input
                type="checkbox"
                name="add_watermark"
                checked={params.add_watermark}
                onChange={handleCheckboxChange}
                className="mr-2"
              />
              <span className="text-sm font-medium text-gray-300">
                ウォーターマークを追加
              </span>
            </label>
          </div>

          {/* 生成ボタン */}
          <button
            onClick={generateImage}
            disabled={isGenerating || !params.prompt}
            className={`w-full py-3 rounded-md font-medium transition-colors ${
              isGenerating || !params.prompt
                ? "bg-gray-600 text-gray-400 cursor-not-allowed"
                : "bg-blue-600 text-white hover:bg-blue-700"
            }`}
          >
            {isGenerating ? "生成中..." : "画像を生成"}
          </button>

          {/* エラーメッセージ */}
          {error && (
            <div className="mt-4 p-3 bg-red-900 text-white rounded-md">
              <p>{error}</p>
            </div>
          )}
        </div>

        {/* 画像表示エリア */}
        <div className="md:col-span-2 bg-gray-800 rounded-lg p-6 shadow-lg">
          <h2 className="text-xl font-bold mb-4 text-gray-100">生成結果</h2>

          {isGenerating ? (
            <div className="flex flex-col items-center justify-center h-64">
              <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-500"></div>
              <p className="mt-4 text-gray-400">画像生成中...</p>
            </div>
          ) : generatedImages.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {generatedImages.map((img, index) => (
                <div key={index} className="relative group">
                  <img
                    src={`data:image/png;base64,${img}`}
                    alt={`生成画像 ${index + 1}`}
                    className="w-full h-auto rounded-lg object-cover cursor-pointer hover:opacity-90 transition-opacity"
                    onClick={() =>
                      setEnlargedImage(`data:image/png;base64,${img}`)
                    }
                  />
                  <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg">
                    <button
                      onClick={() => {
                        const link = document.createElement("a");
                        link.href = `data:image/png;base64,${img}`;
                        link.download = `generated-image-${index}.png`;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                      }}
                      className="px-3 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                    >
                      ダウンロード
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-gray-400">
              <p>画像が生成されていません</p>
              <p className="text-sm mt-2">
                左側のフォームからプロンプトを入力して画像を生成してください
              </p>
            </div>
          )}
        </div>
      </div>

      {/* 拡大表示モーダル */}
      {enlargedImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-80"
          onClick={() => setEnlargedImage(null)}
        >
          <div className="relative max-w-4xl max-h-screen p-2">
            <button
              className="absolute top-2 right-2 text-white bg-red-600 rounded-full w-8 h-8 flex items-center justify-center"
              onClick={(e) => {
                e.stopPropagation();
                setEnlargedImage(null);
              }}
            >
              ×
            </button>
            <img
              src={enlargedImage}
              alt="拡大表示"
              className="max-w-full max-h-[90vh] object-contain"
              onClick={(e) => e.stopPropagation()}
            />
            <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  const link = document.createElement("a");
                  link.href = enlargedImage;
                  link.download = `generated-image.png`;
                  document.body.appendChild(link);
                  link.click();
                  document.body.removeChild(link);
                }}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
              >
                ダウンロード
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GenerateImagePage;