export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.15"
  }
  public: {
    Tables: {
      agent_api_tokens: {
        Row: {
          created_at: string
          device_id: string
          id: string
          label: string
          last_used_at: string | null
          revoked_at: string | null
          token_hash: string
        }
        Insert: {
          created_at?: string
          device_id: string
          id?: string
          label?: string
          last_used_at?: string | null
          revoked_at?: string | null
          token_hash: string
        }
        Update: {
          created_at?: string
          device_id?: string
          id?: string
          label?: string
          last_used_at?: string | null
          revoked_at?: string | null
          token_hash?: string
        }
        Relationships: []
      }
      agent_messages: {
        Row: {
          body: string | null
          command_id: string | null
          created_at: string
          device_id: string
          id: string
          level: string
          message_type: string
          payload: Json
          read_at: string | null
          title: string | null
        }
        Insert: {
          body?: string | null
          command_id?: string | null
          created_at?: string
          device_id: string
          id?: string
          level?: string
          message_type?: string
          payload?: Json
          read_at?: string | null
          title?: string | null
        }
        Update: {
          body?: string | null
          command_id?: string | null
          created_at?: string
          device_id?: string
          id?: string
          level?: string
          message_type?: string
          payload?: Json
          read_at?: string | null
          title?: string | null
        }
        Relationships: []
      }
      agent_sessions: {
        Row: {
          agent_version: string | null
          device_id: string
          ended_at: string | null
          id: string
          last_seen_at: string
          metadata: Json
          started_at: string
        }
        Insert: {
          agent_version?: string | null
          device_id: string
          ended_at?: string | null
          id?: string
          last_seen_at?: string
          metadata?: Json
          started_at?: string
        }
        Update: {
          agent_version?: string | null
          device_id?: string
          ended_at?: string | null
          id?: string
          last_seen_at?: string
          metadata?: Json
          started_at?: string
        }
        Relationships: []
      }
      app_bootstrap: {
        Row: {
          admin_email: string | null
          created_at: string
          id: string
          singleton: boolean
          updated_at: string
        }
        Insert: {
          admin_email?: string | null
          created_at?: string
          id?: string
          singleton?: boolean
          updated_at?: string
        }
        Update: {
          admin_email?: string | null
          created_at?: string
          id?: string
          singleton?: boolean
          updated_at?: string
        }
        Relationships: []
      }
      approvals: {
        Row: {
          decided_at: string | null
          decided_by: string | null
          description: string | null
          id: string
          is_demo: boolean
          job_id: string | null
          metadata: Json
          module_id: string | null
          notes: string | null
          requested_at: string
          status: string
          title: string
        }
        Insert: {
          decided_at?: string | null
          decided_by?: string | null
          description?: string | null
          id?: string
          is_demo?: boolean
          job_id?: string | null
          metadata?: Json
          module_id?: string | null
          notes?: string | null
          requested_at?: string
          status?: string
          title: string
        }
        Update: {
          decided_at?: string | null
          decided_by?: string | null
          description?: string | null
          id?: string
          is_demo?: boolean
          job_id?: string | null
          metadata?: Json
          module_id?: string | null
          notes?: string | null
          requested_at?: string
          status?: string
          title?: string
        }
        Relationships: [
          {
            foreignKeyName: "approvals_job_id_fkey"
            columns: ["job_id"]
            isOneToOne: false
            referencedRelation: "vision_jobs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "approvals_module_id_fkey"
            columns: ["module_id"]
            isOneToOne: false
            referencedRelation: "modules"
            referencedColumns: ["id"]
          },
        ]
      }
      audit_logs: {
        Row: {
          action: string
          created_at: string
          device_id: string | null
          id: string
          ip_address: string | null
          job_id: string | null
          metadata: Json
          module_id: string | null
          outcome: string
          user_id: string | null
        }
        Insert: {
          action: string
          created_at?: string
          device_id?: string | null
          id?: string
          ip_address?: string | null
          job_id?: string | null
          metadata?: Json
          module_id?: string | null
          outcome?: string
          user_id?: string | null
        }
        Update: {
          action?: string
          created_at?: string
          device_id?: string | null
          id?: string
          ip_address?: string | null
          job_id?: string | null
          metadata?: Json
          module_id?: string | null
          outcome?: string
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "audit_logs_device_id_fkey"
            columns: ["device_id"]
            isOneToOne: false
            referencedRelation: "devices"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "audit_logs_job_id_fkey"
            columns: ["job_id"]
            isOneToOne: false
            referencedRelation: "vision_jobs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "audit_logs_module_id_fkey"
            columns: ["module_id"]
            isOneToOne: false
            referencedRelation: "modules"
            referencedColumns: ["id"]
          },
        ]
      }
      commands: {
        Row: {
          acknowledged_at: string | null
          command_type: string
          error: string | null
          executed_at: string | null
          expires_at: string | null
          finished_at: string | null
          id: string
          job_id: string | null
          module_id: string | null
          parameters: Json
          progress: number
          requested_at: string
          requested_by: string | null
          result: Json | null
          started_at: string | null
          status: string
          target_device_code: string | null
          target_device_id: string | null
        }
        Insert: {
          acknowledged_at?: string | null
          command_type: string
          error?: string | null
          executed_at?: string | null
          expires_at?: string | null
          finished_at?: string | null
          id?: string
          job_id?: string | null
          module_id?: string | null
          parameters?: Json
          progress?: number
          requested_at?: string
          requested_by?: string | null
          result?: Json | null
          started_at?: string | null
          status?: string
          target_device_code?: string | null
          target_device_id?: string | null
        }
        Update: {
          acknowledged_at?: string | null
          command_type?: string
          error?: string | null
          executed_at?: string | null
          expires_at?: string | null
          finished_at?: string | null
          id?: string
          job_id?: string | null
          module_id?: string | null
          parameters?: Json
          progress?: number
          requested_at?: string
          requested_by?: string | null
          result?: Json | null
          started_at?: string | null
          status?: string
          target_device_code?: string | null
          target_device_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "commands_job_id_fkey"
            columns: ["job_id"]
            isOneToOne: false
            referencedRelation: "vision_jobs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "commands_module_id_fkey"
            columns: ["module_id"]
            isOneToOne: false
            referencedRelation: "modules"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "commands_target_device_id_fkey"
            columns: ["target_device_id"]
            isOneToOne: false
            referencedRelation: "devices"
            referencedColumns: ["id"]
          },
        ]
      }
      device_modules: {
        Row: {
          device_id: string
          id: string
          module_id: string
          status: string
          updated_at: string
        }
        Insert: {
          device_id: string
          id?: string
          module_id: string
          status?: string
          updated_at?: string
        }
        Update: {
          device_id?: string
          id?: string
          module_id?: string
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "device_modules_device_id_fkey"
            columns: ["device_id"]
            isOneToOne: false
            referencedRelation: "devices"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "device_modules_module_id_fkey"
            columns: ["module_id"]
            isOneToOne: false
            referencedRelation: "modules"
            referencedColumns: ["id"]
          },
        ]
      }
      devices: {
        Row: {
          agent_version: string | null
          code: string
          created_at: string
          current_job_id: string | null
          device_id: string | null
          heartbeat_threshold_seconds: number
          id: string
          is_demo: boolean
          last_seen_at: string | null
          location: string | null
          metadata: Json
          modules: Json
          name: string
          platform_version: string | null
          status: string
          updated_at: string
          vision_version: string | null
        }
        Insert: {
          agent_version?: string | null
          code: string
          created_at?: string
          current_job_id?: string | null
          device_id?: string | null
          heartbeat_threshold_seconds?: number
          id?: string
          is_demo?: boolean
          last_seen_at?: string | null
          location?: string | null
          metadata?: Json
          modules?: Json
          name: string
          platform_version?: string | null
          status?: string
          updated_at?: string
          vision_version?: string | null
        }
        Update: {
          agent_version?: string | null
          code?: string
          created_at?: string
          current_job_id?: string | null
          device_id?: string | null
          heartbeat_threshold_seconds?: number
          id?: string
          is_demo?: boolean
          last_seen_at?: string | null
          location?: string | null
          metadata?: Json
          modules?: Json
          name?: string
          platform_version?: string | null
          status?: string
          updated_at?: string
          vision_version?: string | null
        }
        Relationships: []
      }
      heartbeats: {
        Row: {
          agent_version: string | null
          created_at: string
          device_id: string
          id: string
          modules: Json
          payload: Json
          platform_version: string | null
          status: string
          vision_version: string | null
        }
        Insert: {
          agent_version?: string | null
          created_at?: string
          device_id: string
          id?: string
          modules?: Json
          payload?: Json
          platform_version?: string | null
          status?: string
          vision_version?: string | null
        }
        Update: {
          agent_version?: string | null
          created_at?: string
          device_id?: string
          id?: string
          modules?: Json
          payload?: Json
          platform_version?: string | null
          status?: string
          vision_version?: string | null
        }
        Relationships: []
      }
      job_events: {
        Row: {
          created_at: string
          event_type: string
          id: string
          job_id: string
          message: string | null
          metadata: Json
        }
        Insert: {
          created_at?: string
          event_type: string
          id?: string
          job_id: string
          message?: string | null
          metadata?: Json
        }
        Update: {
          created_at?: string
          event_type?: string
          id?: string
          job_id?: string
          message?: string | null
          metadata?: Json
        }
        Relationships: [
          {
            foreignKeyName: "job_events_job_id_fkey"
            columns: ["job_id"]
            isOneToOne: false
            referencedRelation: "vision_jobs"
            referencedColumns: ["id"]
          },
        ]
      }
      modules: {
        Row: {
          created_at: string
          current_job_id: string | null
          description: string | null
          enabled: boolean
          error_message: string | null
          id: string
          is_demo: boolean
          key: string
          last_activity_at: string | null
          metadata: Json
          name: string
          status: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          current_job_id?: string | null
          description?: string | null
          enabled?: boolean
          error_message?: string | null
          id?: string
          is_demo?: boolean
          key: string
          last_activity_at?: string | null
          metadata?: Json
          name: string
          status?: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          current_job_id?: string | null
          description?: string | null
          enabled?: boolean
          error_message?: string | null
          id?: string
          is_demo?: boolean
          key?: string
          last_activity_at?: string | null
          metadata?: Json
          name?: string
          status?: string
          updated_at?: string
        }
        Relationships: []
      }
      notifications: {
        Row: {
          created_at: string
          device_id: string | null
          id: string
          is_demo: boolean
          job_id: string | null
          message: string | null
          module_id: string | null
          notification_type: string
          read_at: string | null
          title: string
          user_id: string | null
        }
        Insert: {
          created_at?: string
          device_id?: string | null
          id?: string
          is_demo?: boolean
          job_id?: string | null
          message?: string | null
          module_id?: string | null
          notification_type: string
          read_at?: string | null
          title: string
          user_id?: string | null
        }
        Update: {
          created_at?: string
          device_id?: string | null
          id?: string
          is_demo?: boolean
          job_id?: string | null
          message?: string | null
          module_id?: string | null
          notification_type?: string
          read_at?: string | null
          title?: string
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "notifications_device_id_fkey"
            columns: ["device_id"]
            isOneToOne: false
            referencedRelation: "devices"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "notifications_job_id_fkey"
            columns: ["job_id"]
            isOneToOne: false
            referencedRelation: "vision_jobs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "notifications_module_id_fkey"
            columns: ["module_id"]
            isOneToOne: false
            referencedRelation: "modules"
            referencedColumns: ["id"]
          },
        ]
      }
      profiles: {
        Row: {
          created_at: string
          email: string | null
          full_name: string | null
          id: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          email?: string | null
          full_name?: string | null
          id: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          email?: string | null
          full_name?: string | null
          id?: string
          updated_at?: string
        }
        Relationships: []
      }
      user_devices: {
        Row: {
          auth_key: string | null
          created_at: string
          endpoint: string
          id: string
          p256dh: string | null
          user_agent: string | null
          user_id: string
        }
        Insert: {
          auth_key?: string | null
          created_at?: string
          endpoint: string
          id?: string
          p256dh?: string | null
          user_agent?: string | null
          user_id: string
        }
        Update: {
          auth_key?: string | null
          created_at?: string
          endpoint?: string
          id?: string
          p256dh?: string | null
          user_agent?: string | null
          user_id?: string
        }
        Relationships: []
      }
      user_roles: {
        Row: {
          created_at: string
          id: string
          role: Database["public"]["Enums"]["app_role"]
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          role: Database["public"]["Enums"]["app_role"]
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          role?: Database["public"]["Enums"]["app_role"]
          user_id?: string
        }
        Relationships: []
      }
      vision_jobs: {
        Row: {
          code: string
          created_at: string
          current_step: string | null
          device_id: string | null
          duration_seconds: number | null
          error: string | null
          finished_at: string | null
          id: string
          is_demo: boolean
          metadata: Json
          module_id: string | null
          operator_id: string | null
          progress: number
          source: string | null
          started_at: string | null
          status: string
          title: string
          updated_at: string
        }
        Insert: {
          code: string
          created_at?: string
          current_step?: string | null
          device_id?: string | null
          duration_seconds?: number | null
          error?: string | null
          finished_at?: string | null
          id?: string
          is_demo?: boolean
          metadata?: Json
          module_id?: string | null
          operator_id?: string | null
          progress?: number
          source?: string | null
          started_at?: string | null
          status?: string
          title: string
          updated_at?: string
        }
        Update: {
          code?: string
          created_at?: string
          current_step?: string | null
          device_id?: string | null
          duration_seconds?: number | null
          error?: string | null
          finished_at?: string | null
          id?: string
          is_demo?: boolean
          metadata?: Json
          module_id?: string | null
          operator_id?: string | null
          progress?: number
          source?: string | null
          started_at?: string | null
          status?: string
          title?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "vision_jobs_device_id_fkey"
            columns: ["device_id"]
            isOneToOne: false
            referencedRelation: "devices"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "vision_jobs_module_id_fkey"
            columns: ["module_id"]
            isOneToOne: false
            referencedRelation: "modules"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      admin_exists: { Args: never; Returns: boolean }
      agent_fetch_pending_commands: {
        Args: { p_device_id: string; p_limit?: number; p_token: string }
        Returns: Json[]
      }
      agent_heartbeat: {
        Args: {
          p_agent_version?: string
          p_device_id: string
          p_modules?: Json
          p_payload?: Json
          p_platform_version?: string
          p_status?: string
          p_token: string
          p_vision_version?: string
        }
        Returns: Json
      }
      agent_publish_message: {
        Args: {
          p_body: string
          p_command_id?: string
          p_device_id: string
          p_level?: string
          p_message_type?: string
          p_payload?: Json
          p_title?: string
          p_token: string
        }
        Returns: Json
      }
      agent_update_command: {
        Args: {
          p_command_id: string
          p_device_id: string
          p_error?: string
          p_progress?: number
          p_result?: Json
          p_status: string
          p_token: string
        }
        Returns: Json
      }
      agent_verify_token: {
        Args: { p_device_id: string; p_token: string }
        Returns: boolean
      }
      can_operate: { Args: { _user_id: string }; Returns: boolean }
      create_get_status_command: {
        Args: { p_device_id: string }
        Returns: string
      }
      enqueue_supervisor_command: {
        Args: { p_command_type: string; p_device_id: string }
        Returns: string
      }
      has_role: {
        Args: {
          _role: Database["public"]["Enums"]["app_role"]
          _user_id: string
        }
        Returns: boolean
      }
    }
    Enums: {
      app_role: "ADMIN" | "OPERATORE" | "DIREZIONE"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      app_role: ["ADMIN", "OPERATORE", "DIREZIONE"],
    },
  },
} as const
