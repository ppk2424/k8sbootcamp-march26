{{/*
Chart name.
*/}}
{{- define "ecommerce.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified app name.
*/}}
{{- define "ecommerce.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "ecommerce.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "ecommerce.labels" -}}
helm.sh/chart: {{ include "ecommerce.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "ecommerce.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ecommerce.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "ecommerce.namespace" -}}
{{- .Values.global.namespace }}
{{- end }}

{{/*
Compose a container image URI.
Usage: {{ include "ecommerce.image" (dict "image" .Values.services.X.image "tag" .Values.services.X.tag "ctx" $) }}

If `image` already contains a "/" we treat it as a fully-qualified URI and just append :tag.
Otherwise we prepend the ECR registry built from .Values.ecr.accountId and .Values.ecr.region.
*/}}
{{- define "ecommerce.image" -}}
{{- $image := .image -}}
{{- $tag := default "latest" .tag -}}
{{- $ctx := .ctx -}}
{{- if contains "/" $image -}}
{{- printf "%s:%s" $image $tag -}}
{{- else if $ctx.Values.ecr.enabled -}}
{{- printf "%s.dkr.ecr.%s.amazonaws.com/%s:%s" $ctx.Values.ecr.accountId $ctx.Values.ecr.region $image $tag -}}
{{- else -}}
{{- printf "%s:%s" $image $tag -}}
{{- end -}}
{{- end }}
