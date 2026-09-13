export interface Movie {
  id: number
  title: string
  original_title?: string | null
  year?: number | null
  runtime?: number | null
  genres?: string[]
  overview?: string | null
  director?: string | null
  actors?: string[]
  keywords?: string[]
  production_countries?: string[]
  countries?: string[]
  language?: string | null
  original_language?: string | null
  popularity?: number | null
  vote_average?: number | null
  vote_count?: number | null
  catalog_rating?: number | null
  catalog_rating_count?: number | null
  catalog_popularity?: number | null
  catalog_source?: string | null
  community_rating?: number | null
  community_rating_count?: number | null
  community_source?: string | null
  letterboxd_rating?: number | null
  letterboxd_rating_count?: number | null
  letterboxd_url?: string | null
  poster_url?: string | null
  backdrop_url?: string | null
  collection?: string | null
  user_rating?: number | null
  watched?: boolean
  watchlist?: boolean
  match_score?: number
  predicted_rating?: number
  confidence?: string
  category?: string
  explanation?: string
  hate_reason?: string
  components?: Record<string, number>
  similarity?: number
}

export interface MovieReview {
  id?: string | null
  author: string
  username?: string | null
  rating?: number | null
  content: string
  created_at?: string | null
  updated_at?: string | null
  url?: string | null
}

export interface RecommendationResponse { recommendations: Movie[] }
export interface TasteProfile {
  average_rating?: number
  rated_count?: number
  preferred_runtime?: number | null
  rating_distribution?: Record<string, number>
  keyword_scores?: Record<string, number>
  genre_scores?: Record<string, number>
  director_scores?: Record<string, number>
  actor_scores?: Record<string, number>
  decade_scores?: Record<string, number>
  country_scores?: Record<string, number>
  language_scores?: Record<string, number>
  typical_runtime?: number | null
  mainstream_score?: number | null
  highest_rated?: Array<{ title: string; rating: number }>
  lowest_rated?: Array<{ title: string; rating: number }>
  [key: string]: unknown
}

export interface TasteDNA {
  dimensions: Record<string, number>
  summary: string
  mathematically_derived?: boolean
  [key: string]: unknown
}

export interface Stats {
  total_watched?: number
  total_rated?: number
  average_rating?: number
  most_common_rating?: number
  five_star_percentage?: number
  most_watched_director?: string | null
  most_watched_actor?: string | null
  most_watched_genre?: string | null
  favorite_year?: number | null
  favorite_decade?: number | null
  longest_movie?: { title: string; runtime: number } | null
  shortest_movie?: { title: string; runtime: number } | null
  rating_distribution?: Record<string, number>
  [key: string]: unknown
}

export interface EvaluationResult {
  model: string
  mae: number
  rmse: number
  r2: number | null
  train_size: number
  test_size: number
}

export interface EvaluationResponse {
  ready: boolean
  message?: string
  results?: EvaluationResult[]
  best_model?: string
}
