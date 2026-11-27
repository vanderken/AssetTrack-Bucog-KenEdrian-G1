from django.contrib.admin import AdminSite


class AssetTrackAdminSite(AdminSite):
    """Company admin site that renders inside the AssetTrack application shell."""

    site_title = "AssetTrack Administration"
    site_header = "AssetTrack Admin"
    index_title = "Administration"
    site_url = "/accounts/dashboard/"
    enable_nav_sidebar = False


assettrack_admin = AssetTrackAdminSite(name="admin")
