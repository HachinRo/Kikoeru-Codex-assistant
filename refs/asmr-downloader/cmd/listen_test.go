package cmd

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestListenAuthMiddlewareRejectsMissingToken(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(listenAuthMiddleware("secret-token"))
	router.GET("/api/list", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/list", nil)
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 for missing token, got %d", rec.Code)
	}
}

func TestListenAuthMiddlewareAcceptsQueryTokenAndSetsCookie(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(listenAuthMiddleware("secret-token"))
	router.GET("/", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/?token=secret-token", nil)
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for valid query token, got %d", rec.Code)
	}
	if cookies := rec.Result().Cookies(); len(cookies) != 1 || cookies[0].Name != listenTokenCookie {
		t.Fatalf("expected auth cookie %q to be set, got %#v", listenTokenCookie, cookies)
	}
}
