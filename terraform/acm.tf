# terraform/acm.tf — TLS certificate for the public app domain
#
# WHY THIS EXISTS:
#   The shimonvault.<domain> CNAME is written by scripts/deploy.sh with
#   "proxied": false (grey cloud), so browsers connect straight to the ALB —
#   Cloudflare never sees the traffic and therefore never terminates TLS.
#   That means the ALB itself has to present a valid certificate, which is what
#   this file issues and what alb.tf's port-443 listener attaches.
#
#   Validation is DNS-based and fully automated: ACM emits a _acme-challenge
#   style CNAME, the Cloudflare provider writes it into the zone, and
#   aws_acm_certificate_validation blocks until AWS confirms it. Validation
#   records must NOT be proxied or ACM cannot read them.

resource "aws_acm_certificate" "app" {
  domain_name       = local.app_fqdn
  validation_method = "DNS"

  # Re-issue before destroying the old cert so the 443 listener is never
  # left pointing at a certificate that no longer exists.
  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name    = "${var.project_name}-cert"
    Project = var.project_name
  }
}

# One validation record per domain on the cert (currently just app_fqdn, but
# for_each keeps this correct if a SAN is added later).
resource "cloudflare_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.app.domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      value = dvo.resource_record_value
      type  = dvo.resource_record_type
    }
  }

  zone_id = var.cloudflare_zone_id
  name    = each.value.name
  value   = each.value.value
  type    = each.value.type
  proxied = false
  ttl     = 60

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "app" {
  certificate_arn         = aws_acm_certificate.app.arn
  validation_record_fqdns = [for r in cloudflare_record.acm_validation : r.hostname]
}

output "acm_certificate_arn" {
  description = "ARN of the validated ACM certificate served by the ALB on :443"
  value       = aws_acm_certificate_validation.app.certificate_arn
}

output "app_fqdn" {
  description = "Public HTTPS hostname for the app"
  value       = local.app_fqdn
}
