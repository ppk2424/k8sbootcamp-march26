resource "aws_sqs_queue" "karpenter" {
  name                      = "karpenter-${var.cluster_name}"
  message_retention_seconds = 300
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue_policy" "karpenter" {
  queue_url = aws_sqs_queue.karpenter.url

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = ["events.amazonaws.com", "sqs.amazonaws.com"]
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.karpenter.arn
    }]
  })
}

# ---- EventBridge rules → SQS interruption queue ----------------------------

resource "aws_cloudwatch_event_rule" "spot_interruption" {
  name        = "karpenter-${var.cluster_name}-spot-interruption"
  description = "EC2 Spot Instance Interruption Warning"
  event_pattern = jsonencode({
    source        = ["aws.ec2"]
    "detail-type" = ["EC2 Spot Instance Interruption Warning"]
  })
}

resource "aws_cloudwatch_event_target" "spot_interruption" {
  rule      = aws_cloudwatch_event_rule.spot_interruption.name
  target_id = "KarpenterInterruptionQueueTarget"
  arn       = aws_sqs_queue.karpenter.arn
}

resource "aws_cloudwatch_event_rule" "rebalance" {
  name        = "karpenter-${var.cluster_name}-rebalance"
  description = "EC2 Instance Rebalance Recommendation"
  event_pattern = jsonencode({
    source        = ["aws.ec2"]
    "detail-type" = ["EC2 Instance Rebalance Recommendation"]
  })
}

resource "aws_cloudwatch_event_target" "rebalance" {
  rule      = aws_cloudwatch_event_rule.rebalance.name
  target_id = "KarpenterInterruptionQueueTarget"
  arn       = aws_sqs_queue.karpenter.arn
}

resource "aws_cloudwatch_event_rule" "scheduled_change" {
  name        = "karpenter-${var.cluster_name}-scheduled-change"
  description = "AWS Health Scheduled Change"
  event_pattern = jsonencode({
    source        = ["aws.health"]
    "detail-type" = ["AWS Health Event"]
  })
}

resource "aws_cloudwatch_event_target" "scheduled_change" {
  rule      = aws_cloudwatch_event_rule.scheduled_change.name
  target_id = "KarpenterInterruptionQueueTarget"
  arn       = aws_sqs_queue.karpenter.arn
}

resource "aws_cloudwatch_event_rule" "instance_state_change" {
  name        = "karpenter-${var.cluster_name}-instance-state-change"
  description = "EC2 Instance State-change Notification"
  event_pattern = jsonencode({
    source        = ["aws.ec2"]
    "detail-type" = ["EC2 Instance State-change Notification"]
  })
}

resource "aws_cloudwatch_event_target" "instance_state_change" {
  rule      = aws_cloudwatch_event_rule.instance_state_change.name
  target_id = "KarpenterInterruptionQueueTarget"
  arn       = aws_sqs_queue.karpenter.arn
}
