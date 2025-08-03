package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"os/signal"
	"os/user"
	"path/filepath"
	"sort"
	"sync"
	"syscall"
	"time"

	"github.com/florianl/go-tc"
	"github.com/google/uuid"
	"github.com/sirupsen/logrus"
	"github.com/vishvananda/netlink"
)

// 全局变量用于优雅关闭
var shutdownCtx, shutdownCancel = context.WithCancel(context.Background())

// ConvergenceSession 收敛测量会话
type ConvergenceSession struct {
	SessionID               int                    `json:"session_id"`
	NetemEventTime          int64                  `json:"netem_event_time"`
	NetemInfo               map[string]interface{} `json:"netem_info"`
	RouteEvents             []RouteEvent           `json:"route_events"`
	LastRouteEventTime      *int64                 `json:"last_route_event_time"`
	ConvergenceTime         *int64                 `json:"convergence_time"`
	IsConverged             bool                   `json:"is_converged"`
	ConvergenceDetectedTime *int64                 `json:"convergence_detected_time"`
	convergenceCheckCount   int
	mu                      sync.RWMutex
}

// RouteEvent 路由事件
type RouteEvent struct {
	Timestamp       int64                  `json:"timestamp"`
	Type            string                 `json:"type"`
	Info            map[string]interface{} `json:"info"`
	OffsetFromNetem int64                  `json:"offset_from_netem"`
}

// QdiscEvent qdisc事件
type QdiscEvent struct {
	Timestamp int64                  `json:"timestamp"`
	Type      string                 `json:"type"`
	Info      map[string]interface{} `json:"info"`
}

// NewConvergenceSession 创建新的收敛会话
func NewConvergenceSession(sessionID int, netemEventTime int64, netemInfo map[string]interface{}) *ConvergenceSession {
	return &ConvergenceSession{
		SessionID:      sessionID,
		NetemEventTime: netemEventTime,
		NetemInfo:      netemInfo,
		RouteEvents:    make([]RouteEvent, 0),
	}
}

// AddRouteEvent 添加路由事件
func (cs *ConvergenceSession) AddRouteEvent(timestamp int64, eventType string, routeInfo map[string]interface{}) {
	cs.mu.Lock()
	defer cs.mu.Unlock()

	event := RouteEvent{
		Timestamp:       timestamp,
		Type:            eventType,
		Info:            routeInfo,
		OffsetFromNetem: timestamp - cs.NetemEventTime,
	}
	cs.RouteEvents = append(cs.RouteEvents, event)
	cs.LastRouteEventTime = &timestamp
}

// CheckConvergence 检查是否收敛
func (cs *ConvergenceSession) CheckConvergence(quietPeriodMs int64) bool {
	cs.mu.Lock()
	defer cs.mu.Unlock()

	if cs.IsConverged {
		return true
	}

	currentTime := time.Now().UnixMilli()
	var quietTime int64

	if cs.LastRouteEventTime == nil {
		quietTime = currentTime - cs.NetemEventTime
	} else {
		quietTime = currentTime - *cs.LastRouteEventTime
	}

	cs.convergenceCheckCount++

	if quietTime >= quietPeriodMs {
		cs.IsConverged = true
		detectedTime := currentTime
		cs.ConvergenceDetectedTime = &detectedTime

		if cs.LastRouteEventTime != nil {
			// 收敛时间 = 最后一次路由事件时间 - 第一次触发事件时间
			convergenceTime := *cs.LastRouteEventTime - cs.NetemEventTime
			cs.ConvergenceTime = &convergenceTime
		} else {
			// 如果没有发生路由事件，收敛时间为 0
			var zeroTime int64 = 0
			cs.ConvergenceTime = &zeroTime
		}

		return true
	}

	return false
}

// GetRouteEventCount 获取路由事件数量
func (cs *ConvergenceSession) GetRouteEventCount() int {
	cs.mu.RLock()
	defer cs.mu.RUnlock()
	return len(cs.RouteEvents)
}

// GetSessionDuration 获取会话总持续时间
func (cs *ConvergenceSession) GetSessionDuration() int64 {
	cs.mu.RLock()
	defer cs.mu.RUnlock()

	if cs.ConvergenceDetectedTime != nil {
		return *cs.ConvergenceDetectedTime - cs.NetemEventTime
	}
	return time.Now().UnixMilli() - cs.NetemEventTime
}

// NetemConvergenceMonitor 路由收敛监控器
type NetemConvergenceMonitor struct {
	logger                   *logrus.Logger
	logFilePath              string
	routerName               string
	monitorID                string
	convergenceThresholdMs   int64
	currentSession           *ConvergenceSession
	completedSessions        []*ConvergenceSession
	sessionCounter           int
	state                    string // IDLE, MONITORING
	totalRouteEvents         int
	totalNetemTriggers       int
	totalRouteTriggers       int
	monitoringStartTime      int64
	recentQdiscEvents        []QdiscEvent
	sessionMu                sync.RWMutex
	convergenceCheckerCancel context.CancelFunc
}

// 全局logger
var logger *logrus.Logger

// PlainJSONFormatter 纯JSON格式化器，不添加任何前缀
type PlainJSONFormatter struct{}

func (f *PlainJSONFormatter) Format(entry *logrus.Entry) ([]byte, error) {
	// 直接返回消息内容，不添加任何前缀或后缀
	return []byte(entry.Message + "\n"), nil
}

// setupAsyncLogging 配置异步结构化日志系统
func setupAsyncLogging(customLogPath string) (*logrus.Logger, string) {
	localLogger := logrus.New()

	var logFile string

	if customLogPath != "" {
		// 使用用户指定的日志文件路径
		logFile = customLogPath

		// 确保日志文件的目录存在
		logDir := filepath.Dir(logFile)
		if err := os.MkdirAll(logDir, 0755); err != nil {
			fmt.Printf("无法创建日志目录 %s: %v，使用当前目录\n", logDir, err)
			logFile = filepath.Join(".", filepath.Base(logFile))
		}
	} else {
		// 使用默认日志路径
		logDir := "/var/log/frr"
		if _, err := os.Stat(logDir); os.IsNotExist(err) {
			if err := os.MkdirAll(logDir, 0755); err != nil {
				logDir = "."
				fmt.Printf("无法创建 /var/log/frr 目录，使用当前目录: %s\n", logDir)
			}
		}
		logFile = filepath.Join(logDir, "async_route_convergence.json")
	}

	// 使用自定义格式化器，直接输出纯JSON，不添加任何前缀
	localLogger.SetFormatter(&PlainJSONFormatter{})
	localLogger.SetLevel(logrus.InfoLevel)

	// 尝试创建日志文件
	if file, err := os.OpenFile(logFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666); err == nil {
		localLogger.SetOutput(file)
		fmt.Printf("JSON结构化日志文件已配置: %s\n", logFile)
	} else {
		fmt.Printf("无法写入日志文件 %s，仅使用控制台输出: %v\n", logFile, err)
		localLogger.SetOutput(os.Stdout)
	}

	return localLogger, logFile
}

// logStructuredDataAsync 异步记录结构化JSON日志
func logStructuredDataAsync(logger *logrus.Logger, data map[string]interface{}) {
	go func() {
		if jsonData, err := json.Marshal(data); err == nil {
			logger.Info(string(jsonData))
		} else {
			fmt.Printf("❌ 记录JSON日志失败: %v\n", err)
		}
	}()
}

// NewNetemConvergenceMonitor 创建新的监控器
func NewNetemConvergenceMonitor(convergenceThresholdMs int64, routerName, logPath string) *NetemConvergenceMonitor {
	localLogger, logFilePath := setupAsyncLogging(logPath)

	// 设置全局logger
	logger = localLogger

	if routerName == "" {
		currentUser, _ := user.Current()
		routerName = fmt.Sprintf("router_%s_%d", currentUser.Username, time.Now().Unix())
	}

	return &NetemConvergenceMonitor{
		logger:                 localLogger,
		logFilePath:            logFilePath,
		routerName:             routerName,
		monitorID:              uuid.New().String(),
		convergenceThresholdMs: convergenceThresholdMs,
		state:                  "IDLE",
		monitoringStartTime:    time.Now().UnixMilli(),
		recentQdiscEvents:      make([]QdiscEvent, 0, 20),
		completedSessions:      make([]*ConvergenceSession, 0),
	}
}

// formatTimestamp 格式化时间戳
func (ncm *NetemConvergenceMonitor) formatTimestamp(timestampMs int64) string {
	t := time.UnixMilli(timestampMs)
	return t.Format("2006-01-02 15:04:05.000")
}

// getInterfaceName 根据接口索引获取接口名称
func (ncm *NetemConvergenceMonitor) getInterfaceName(ifindex int) string {
	if link, err := netlink.LinkByIndex(ifindex); err == nil {
		return link.Attrs().Name
	}
	return fmt.Sprintf("if%d", ifindex)
}

// parseRouteInfo 解析路由消息信息
func (ncm *NetemConvergenceMonitor) parseRouteInfo(route *netlink.Route) map[string]interface{} {
	routeInfo := make(map[string]interface{})

	// 获取目标网络
	if route.Dst != nil {
		routeInfo["dst"] = route.Dst.String()
	} else {
		routeInfo["dst"] = "default"
	}

	// 获取网关
	if route.Gw != nil {
		routeInfo["gateway"] = route.Gw.String()
	} else {
		routeInfo["gateway"] = "N/A"
	}

	// 获取接口
	if route.LinkIndex > 0 {
		routeInfo["interface"] = ncm.getInterfaceName(route.LinkIndex)
		routeInfo["ifindex"] = route.LinkIndex
	} else {
		routeInfo["interface"] = "N/A"
		routeInfo["ifindex"] = 0
	}

	routeInfo["table"] = route.Table
	// Note: netlink.Route doesn't have Family field, using a default value
	routeInfo["family"] = 2 // AF_INET

	return routeInfo
}

// parseQdiscInfo 解析qdisc消息信息 (使用 go-tc 库)
func (ncm *NetemConvergenceMonitor) parseQdiscInfoFromTC(obj *tc.Object) map[string]interface{} {
	qdiscInfo := make(map[string]interface{})

	qdiscInfo["interface"] = ncm.getInterfaceName(int(obj.Ifindex))
	qdiscInfo["ifindex"] = obj.Ifindex
	qdiscInfo["handle"] = obj.Handle
	qdiscInfo["parent"] = obj.Parent

	// 检查qdisc类型
	var qdiscType string
	if obj.Kind != "" {
		qdiscType = obj.Kind
	} else {
		qdiscType = "unknown"
	}
	qdiscInfo["kind"] = qdiscType
	qdiscInfo["is_netem"] = qdiscType == "netem"

	return qdiscInfo
}

// parseQdiscInfo 解析qdisc消息信息 (兼容 netlink 库)
func (ncm *NetemConvergenceMonitor) parseQdiscInfo(qdisc netlink.Qdisc) map[string]interface{} {
	attrs := qdisc.Attrs()
	qdiscInfo := make(map[string]interface{})

	qdiscInfo["interface"] = ncm.getInterfaceName(attrs.LinkIndex)
	qdiscInfo["ifindex"] = attrs.LinkIndex
	qdiscInfo["handle"] = attrs.Handle
	qdiscInfo["parent"] = attrs.Parent

	// 检查qdisc类型
	qdiscType := qdisc.Type()
	qdiscInfo["kind"] = qdiscType
	qdiscInfo["is_netem"] = qdiscType == "netem"

	return qdiscInfo
}

// isNetemRelatedEvent 判断是否为netem相关事件
func (ncm *NetemConvergenceMonitor) isNetemRelatedEvent(qdiscInfo map[string]interface{}, eventType string) bool {
	// 直接检查是否为netem类型
	if isNetem, ok := qdiscInfo["is_netem"].(bool); ok && isNetem {
		return true
	}

	// 删除事件可能没有kind信息，检查最近是否有同接口的netem事件
	if eventType == "QDISC_DEL" {
		interfaceName := qdiscInfo["interface"].(string)
		for i := len(ncm.recentQdiscEvents) - 1; i >= 0; i-- {
			recentEvent := ncm.recentQdiscEvents[i]
			if recentInterface, ok := recentEvent.Info["interface"].(string); ok &&
				recentInterface == interfaceName {
				if isNetem, ok := recentEvent.Info["is_netem"].(bool); ok && isNetem {
					return true
				}
			}
		}
	}

	return false
}

// handleTriggerEvent 处理触发事件 - 开始新的收敛测量会话
func (ncm *NetemConvergenceMonitor) handleTriggerEvent(timestamp int64, eventType string, triggerInfo map[string]interface{}, triggerSource string) {
	ncm.sessionMu.Lock()
	defer ncm.sessionMu.Unlock()

	// 如果当前有会话在进行且未收敛，不强制终止
	if ncm.currentSession != nil && !ncm.currentSession.IsConverged {
		fmt.Printf("⚠️  忽略新%s事件，会话 #%d 仍在进行中\n", eventType, ncm.currentSession.SessionID)
		return
	}

	// 开始新会话
	ncm.sessionCounter++
	ncm.currentSession = NewConvergenceSession(ncm.sessionCounter, timestamp, triggerInfo)
	ncm.state = "MONITORING"

	// 更新统计
	if triggerSource == "netem" {
		ncm.totalNetemTriggers++
	} else {
		ncm.totalRouteTriggers++
	}

	// 记录会话开始的结构化日志
	currentUser, _ := user.Current()
	sessionStartData := map[string]interface{}{
		"event_type":         "session_started",
		"router_name":        ncm.routerName,
		"session_id":         ncm.sessionCounter,
		"trigger_source":     triggerSource,
		"trigger_event_type": eventType,
		"trigger_info":       triggerInfo,
		"timestamp":          time.UnixMilli(timestamp).UTC().Format(time.RFC3339),
		"user":               currentUser.Username,
	}
	logStructuredDataAsync(ncm.logger, sessionStartData)

	// 控制台输出关键信息
	if triggerSource == "netem" {
		fmt.Printf("🚀 开始会话 #%d (Netem触发: %s)\n", ncm.sessionCounter, eventType)
		if iface, ok := triggerInfo["interface"].(string); ok {
			fmt.Printf("   接口: %s\n", iface)
		}
	} else { // 路由触发
		fmt.Printf("🚀 开始会话 #%d (路由触发: %s)\n", ncm.sessionCounter, eventType)
		if dst, ok := triggerInfo["dst"].(string); ok {
			fmt.Printf("   目标: %s\n", dst)
		}
	}
}

// handleQdiscEventFromTC 处理来自 go-tc 的 qdisc 事件
func (ncm *NetemConvergenceMonitor) handleQdiscEventFromTC(obj *tc.Object, eventType string) {
	currentTime := time.Now().UnixMilli()
	qdiscInfo := ncm.parseQdiscInfoFromTC(obj)

	// 缓存qdisc事件
	event := QdiscEvent{
		Timestamp: currentTime,
		Type:      eventType,
		Info:      qdiscInfo,
	}
	ncm.recentQdiscEvents = append(ncm.recentQdiscEvents, event)
	if len(ncm.recentQdiscEvents) > 20 {
		ncm.recentQdiscEvents = ncm.recentQdiscEvents[1:]
	}

	// 检查是否为netem相关事件
	if ncm.isNetemRelatedEvent(qdiscInfo, eventType) {
		// 记录netem事件的结构化日志
		currentUser, _ := user.Current()
		netemEventData := map[string]interface{}{
			"event_type":       "netem_detected",
			"router_name":      ncm.routerName,
			"netem_event_type": eventType,
			"timestamp":        time.UnixMilli(currentTime).UTC().Format(time.RFC3339),
			"qdisc_info":       qdiscInfo,
			"user":             currentUser.Username,
		}
		logStructuredDataAsync(ncm.logger, netemEventData)

		// 根据当前状态决定处理方式
		ncm.sessionMu.Lock()
		if ncm.state == "MONITORING" && ncm.currentSession != nil && !ncm.currentSession.IsConverged {
			// 当前有活跃会话，将netem事件作为普通路由事件处理
			ncm.currentSession.AddRouteEvent(currentTime, fmt.Sprintf("Netem事件(%s)", eventType), qdiscInfo)
			ncm.totalRouteEvents++

			offset := currentTime - ncm.currentSession.NetemEventTime
			sessionID := ncm.currentSession.SessionID
			eventCount := ncm.currentSession.GetRouteEventCount()
			ncm.sessionMu.Unlock()

			// 记录作为路由事件的结构化日志
			routeEventData := map[string]interface{}{
				"event_type":             "route_event",
				"router_name":            ncm.routerName,
				"session_id":             sessionID,
				"route_event_type":       fmt.Sprintf("Netem事件(%s)", eventType),
				"route_event_number":     ncm.totalRouteEvents,
				"session_event_number":   eventCount,
				"offset_from_trigger_ms": offset,
				"timestamp":              time.UnixMilli(currentTime).UTC().Format(time.RFC3339),
				"route_info":             qdiscInfo,
				"user":                   currentUser.Username,
			}
			logStructuredDataAsync(ncm.logger, routeEventData)
		} else {
			ncm.sessionMu.Unlock()
			// 没有活跃会话，作为触发事件处理
			ncm.handleTriggerEvent(currentTime, eventType, qdiscInfo, "netem")
		}
	}
}

// handleQdiscEvent 处理qdisc事件 (兼容 netlink 库)
func (ncm *NetemConvergenceMonitor) handleQdiscEvent(qdisc netlink.Qdisc, eventType string) {
	currentTime := time.Now().UnixMilli()
	qdiscInfo := ncm.parseQdiscInfo(qdisc)

	// 缓存qdisc事件
	event := QdiscEvent{
		Timestamp: currentTime,
		Type:      eventType,
		Info:      qdiscInfo,
	}
	ncm.recentQdiscEvents = append(ncm.recentQdiscEvents, event)
	if len(ncm.recentQdiscEvents) > 20 {
		ncm.recentQdiscEvents = ncm.recentQdiscEvents[1:]
	}

	// 检查是否为netem相关事件
	if ncm.isNetemRelatedEvent(qdiscInfo, eventType) {
		// 记录netem事件的结构化日志
		currentUser, _ := user.Current()
		netemEventData := map[string]interface{}{
			"event_type":       "netem_detected",
			"router_name":      ncm.routerName,
			"netem_event_type": eventType,
			"timestamp":        time.UnixMilli(currentTime).UTC().Format(time.RFC3339),
			"qdisc_info":       qdiscInfo,
			"user":             currentUser.Username,
		}
		logStructuredDataAsync(ncm.logger, netemEventData)

		// 根据当前状态决定处理方式
		ncm.sessionMu.Lock()
		if ncm.state == "MONITORING" && ncm.currentSession != nil && !ncm.currentSession.IsConverged {
			// 当前有活跃会话，将netem事件作为普通路由事件处理
			ncm.currentSession.AddRouteEvent(currentTime, fmt.Sprintf("Netem事件(%s)", eventType), qdiscInfo)
			ncm.totalRouteEvents++

			offset := currentTime - ncm.currentSession.NetemEventTime
			sessionID := ncm.currentSession.SessionID
			eventCount := ncm.currentSession.GetRouteEventCount()
			ncm.sessionMu.Unlock()

			// 记录作为路由事件的结构化日志
			routeEventData := map[string]interface{}{
				"event_type":             "route_event",
				"router_name":            ncm.routerName,
				"session_id":             sessionID,
				"route_event_type":       fmt.Sprintf("Netem事件(%s)", eventType),
				"route_event_number":     ncm.totalRouteEvents,
				"session_event_number":   eventCount,
				"offset_from_trigger_ms": offset,
				"timestamp":              time.UnixMilli(currentTime).UTC().Format(time.RFC3339),
				"route_info":             qdiscInfo,
				"user":                   currentUser.Username,
			}
			logStructuredDataAsync(ncm.logger, routeEventData)
		} else {
			ncm.sessionMu.Unlock()
			// 没有活跃会话，作为触发事件处理
			ncm.handleTriggerEvent(currentTime, eventType, qdiscInfo, "netem")
		}
	}
}

// handleRouteEvent 处理路由事件
func (ncm *NetemConvergenceMonitor) handleRouteEvent(timestamp int64, eventType string, routeInfo map[string]interface{}) {
	// 检查是否应该作为触发事件
	if (eventType == "路由添加" || eventType == "路由删除") &&
		ncm.state == "IDLE" {

		// 作为触发事件处理
		var triggerType string
		if eventType == "路由添加" {
			triggerType = "route_add"
		} else {
			triggerType = "route_del"
		}

		triggerInfo := map[string]interface{}{
			"type": triggerType,
		}
		if routeInfo != nil {
			if dst, ok := routeInfo["dst"]; ok {
				triggerInfo["dst"] = dst
			} else {
				triggerInfo["dst"] = "N/A"
			}
			if iface, ok := routeInfo["interface"]; ok {
				triggerInfo["interface"] = iface
			} else {
				triggerInfo["interface"] = "N/A"
			}
			if gw, ok := routeInfo["gateway"]; ok {
				triggerInfo["gateway"] = gw
			} else {
				triggerInfo["gateway"] = "N/A"
			}
		} else {
			triggerInfo["dst"] = "N/A"
			triggerInfo["interface"] = "N/A"
			triggerInfo["gateway"] = "N/A"
		}

		ncm.handleTriggerEvent(timestamp, eventType, triggerInfo, "route")
		return
	}

	// 普通路由事件处理
	ncm.sessionMu.Lock()
	if ncm.state != "MONITORING" || ncm.currentSession == nil {
		ncm.sessionMu.Unlock()
		return // 不在监控状态，忽略路由事件
	}

	ncm.currentSession.AddRouteEvent(timestamp, eventType, routeInfo)
	ncm.totalRouteEvents++

	offset := timestamp - ncm.currentSession.NetemEventTime
	sessionID := ncm.currentSession.SessionID
	eventCount := ncm.currentSession.GetRouteEventCount()
	ncm.sessionMu.Unlock()

	// 记录路由事件的结构化日志
	currentUser, _ := user.Current()
	routeEventData := map[string]interface{}{
		"event_type":             "route_event",
		"router_name":            ncm.routerName,
		"session_id":             sessionID,
		"route_event_type":       eventType,
		"route_event_number":     ncm.totalRouteEvents,
		"session_event_number":   eventCount,
		"offset_from_trigger_ms": offset,
		"timestamp":              time.UnixMilli(timestamp).UTC().Format(time.RFC3339),
		"route_info":             routeInfo,
		"user":                   currentUser.Username,
	}
	logStructuredDataAsync(ncm.logger, routeEventData)
}

// convergenceChecker 后台收敛检查任务
func (ncm *NetemConvergenceMonitor) convergenceChecker(ctx context.Context) {
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			ncm.sessionMu.Lock()
			if ncm.state == "MONITORING" &&
				ncm.currentSession != nil &&
				!ncm.currentSession.IsConverged {

				if ncm.currentSession.CheckConvergence(ncm.convergenceThresholdMs) {
					// 收敛完成，控制台输出简洁信息
					fmt.Printf("✅ 会话 #%d 收敛完成\n", ncm.currentSession.SessionID)
					ncm.finishCurrentSession()
				}
			}
			ncm.sessionMu.Unlock()
		}
	}
}

// finishCurrentSession 完成当前收敛测量会话
func (ncm *NetemConvergenceMonitor) finishCurrentSession() {
	if ncm.currentSession == nil {
		return
	}

	session := ncm.currentSession
	ncm.completedSessions = append(ncm.completedSessions, session)

	// 记录会话完成的结构化日志
	currentUser, _ := user.Current()
	sessionData := map[string]interface{}{
		"event_type":               "session_completed",
		"router_name":              ncm.routerName,
		"session_id":               session.SessionID,
		"convergence_time_ms":      session.ConvergenceTime,
		"route_events_count":       len(session.RouteEvents),
		"session_duration_ms":      session.GetSessionDuration(),
		"convergence_threshold_ms": ncm.convergenceThresholdMs,
		"netem_info":               session.NetemInfo,
		"route_events":             session.RouteEvents,
		"timestamp":                time.Now().UTC().Format(time.RFC3339),
		"user":                     currentUser.Username,
	}
	logStructuredDataAsync(ncm.logger, sessionData)

	// 控制台输出关键信息
	if session.ConvergenceTime != nil {
		fmt.Printf("   收敛时间: %dms, 路由事件: %d\n", *session.ConvergenceTime, len(session.RouteEvents))
	} else {
		fmt.Printf("   路由事件: %d\n", len(session.RouteEvents))
	}

	// 重置状态，准备下一次监控
	ncm.currentSession = nil
	ncm.state = "IDLE"
}

// forceFinishSession 强制结束当前会话
func (ncm *NetemConvergenceMonitor) forceFinishSession(reason string) {
	if ncm.currentSession != nil {
		ncm.currentSession.CheckConvergence(0) // 强制收敛
		fmt.Printf("📋 强制结束会话 #%d: %s\n", ncm.currentSession.SessionID, reason)
		ncm.finishCurrentSession()
	}
}

// monitorEvents 开始监听所有相关事件
func (ncm *NetemConvergenceMonitor) monitorEvents(ctx context.Context) error {
	utcNow := time.Now().UTC()

	// 记录监听开始的结构化日志
	currentUser, _ := user.Current()
	startData := map[string]interface{}{
		"event_type":               "monitoring_started",
		"router_name":              ncm.routerName,
		"user":                     currentUser.Username,
		"utc_time":                 utcNow.Format(time.RFC3339),
		"listen_start_time":        time.UnixMilli(ncm.monitoringStartTime).UTC().Format(time.RFC3339),
		"convergence_threshold_ms": ncm.convergenceThresholdMs,
		"log_file_path":            ncm.logFilePath,
		"monitor_id":               ncm.monitorID,
	}
	logStructuredDataAsync(ncm.logger, startData)

	// 控制台输出关键信息
	fmt.Printf("🎯 监控开始 - 路由器: %s\n", ncm.routerName)
	fmt.Printf("   收敛阈值: %dms\n", ncm.convergenceThresholdMs)
	fmt.Println("   等待触发事件...")

	// 启动后台收敛检查任务
	convergenceCtx, convergenceCancel := context.WithCancel(ctx)
	ncm.convergenceCheckerCancel = convergenceCancel
	go ncm.convergenceChecker(convergenceCtx)

	// 创建 go-tc 实例来监听 qdisc 事件
	tcHandle, err := tc.Open(&tc.Config{})
	if err != nil {
		return fmt.Errorf("打开 tc 连接失败: %v", err)
	}
	defer tcHandle.Close()

	// 监听路由变化
	routeUpdates := make(chan netlink.RouteUpdate)
	routeDone := make(chan struct{})
	if err := netlink.RouteSubscribe(routeUpdates, routeDone); err != nil {
		return fmt.Errorf("订阅路由更新失败: %v", err)
	}

	defer func() {
		close(routeDone)
		if ncm.convergenceCheckerCancel != nil {
			ncm.convergenceCheckerCancel()
		}
		ncm.printStatistics()
	}()

	// 启动 TC 事件监听 goroutine
	tcCtx, tcCancel := context.WithCancel(ctx)
	defer tcCancel()

	go func() {
		// TC 事件处理函数
		hookFunc := func(action uint16, obj tc.Object) int {
			var eventType string

			if obj.Kind == "noqueue" {
				return 0
			}

			switch action {
			case syscall.RTM_NEWQDISC:
				eventType = "QDISC_ADD"
			case syscall.RTM_DELQDISC:
				eventType = "QDISC_DEL"
			case syscall.RTM_GETQDISC:
				eventType = "QDISC_GET"
			default:
				return 0 // 忽略其他类型的消息
			}

			// 处理 qdisc 事件
			ncm.handleQdiscEventFromTC(&obj, eventType)
			return 0
		}

		// 错误处理函数
		errorFunc := func(err error) int {
			if err != nil {
				fmt.Printf("❌ TC 监听错误: %v\n", err)
			}
			return 0
		}

		// 开始监听 TC 事件，设置 1 小时的超时
		deadline := time.Hour
		if err := tcHandle.MonitorWithErrorFunc(tcCtx, deadline, hookFunc, errorFunc); err != nil {
			fmt.Printf("❌ TC 监听失败: %v\n", err)
		}
	}()

	// 主事件循环
	for {
		select {
		case <-ctx.Done():
			return nil
		case update := <-routeUpdates:
			currentTime := time.Now().UnixMilli()
			routeInfo := ncm.parseRouteInfo(&update.Route)

			switch update.Type {
			case syscall.RTM_NEWROUTE:
				ncm.handleRouteEvent(currentTime, "路由添加", routeInfo)
			case syscall.RTM_DELROUTE:
				ncm.handleRouteEvent(currentTime, "路由删除", routeInfo)
			}
		}
	}
}

// printStatistics 打印最终统计报告并记录结构化日志
func (ncm *NetemConvergenceMonitor) printStatistics() {
	// 强制结束当前会话
	ncm.sessionMu.Lock()
	if ncm.currentSession != nil && !ncm.currentSession.IsConverged {
		ncm.forceFinishSession("监听结束")
	}
	ncm.sessionMu.Unlock()

	currentTime := time.Now().UnixMilli()
	totalTime := currentTime - ncm.monitoringStartTime
	utcNow := time.Now().UTC()

	// 计算统计数据
	var convergenceTimes []int64
	var routeCounts []int
	var sessionDurations []int64
	var allInterfaces []string
	interfaceSet := make(map[string]bool)
	var sessionsList []map[string]interface{}

	for _, session := range ncm.completedSessions {
		if session.ConvergenceTime != nil {
			convergenceTimes = append(convergenceTimes, *session.ConvergenceTime)
		}
		routeCounts = append(routeCounts, session.GetRouteEventCount())
		sessionDurations = append(sessionDurations, session.GetSessionDuration())

		// 收集接口信息
		if iface, ok := session.NetemInfo["interface"].(string); ok {
			interfaceSet[iface] = true
		}

		for _, routeEvent := range session.RouteEvents {
			if routeEvent.Info != nil {
				if iface, ok := routeEvent.Info["interface"].(string); ok {
					interfaceSet[iface] = true
				}
			}
		}

		// 会话信息
		sessionInfo := map[string]interface{}{
			"session_id":          session.SessionID,
			"convergence_time_ms": session.ConvergenceTime,
			"route_events_count":  session.GetRouteEventCount(),
			"session_duration_ms": session.GetSessionDuration(),
			"netem_info":          session.NetemInfo,
		}
		sessionsList = append(sessionsList, sessionInfo)
	}

	for iface := range interfaceSet {
		allInterfaces = append(allInterfaces, iface)
	}
	sort.Strings(allInterfaces)

	// 收敛时间分布
	fastConvergence := 0
	mediumConvergence := 0
	slowConvergence := 0
	for _, t := range convergenceTimes {
		if t < 100 {
			fastConvergence++
		} else if t < 1000 {
			mediumConvergence++
		} else {
			slowConvergence++
		}
	}

	// 构建结构化日志数据
	currentUser, _ := user.Current()
	structuredData := map[string]interface{}{
		"event_type":                    "monitoring_completed",
		"router_name":                   ncm.routerName,
		"log_file_path":                 ncm.logFilePath,
		"user":                          currentUser.Username,
		"utc_time":                      utcNow.Format(time.RFC3339),
		"listen_start_time":             time.UnixMilli(ncm.monitoringStartTime).UTC().Format(time.RFC3339),
		"listen_end_time":               time.UnixMilli(currentTime).UTC().Format(time.RFC3339),
		"total_listen_duration_ms":      totalTime,
		"total_listen_duration_seconds": float64(totalTime) / 1000.0,
		"convergence_threshold_ms":      ncm.convergenceThresholdMs,
		"total_trigger_events":          ncm.totalNetemTriggers + ncm.totalRouteTriggers,
		"netem_events_count":            ncm.totalNetemTriggers,
		"route_events_in_trigger":       ncm.totalRouteTriggers,
		"total_route_events":            ncm.totalRouteEvents,
		"completed_sessions_count":      len(ncm.completedSessions),
		"fast_convergence_count":        fastConvergence,
		"medium_convergence_count":      mediumConvergence,
		"slow_convergence_count":        slowConvergence,
		"session_count":                 len(ncm.completedSessions),
		"sessions_list":                 sessionsList,
		"interfaces_list":               allInterfaces,
		"convergence_times_list":        convergenceTimes,
		"unique_interfaces":             allInterfaces,
		"unique_interface_count":        len(allInterfaces),
		"extraction_timestamp":          utcNow.Format(time.RFC3339),
		"extracted_by":                  fmt.Sprintf("async_event_monitor_v1.0_%s", ncm.monitorID),
	}

	// 添加统计信息
	if len(convergenceTimes) > 0 {
		sort.Slice(convergenceTimes, func(i, j int) bool { return convergenceTimes[i] < convergenceTimes[j] })
		structuredData["fastest_convergence_ms"] = convergenceTimes[0]
		structuredData["slowest_convergence_ms"] = convergenceTimes[len(convergenceTimes)-1]

		// 计算平均值
		var sum int64
		for _, t := range convergenceTimes {
			sum += t
		}
		structuredData["avg_convergence_time_ms"] = float64(sum) / float64(len(convergenceTimes))

		// 计算标准差
		if len(convergenceTimes) > 1 {
			mean := float64(sum) / float64(len(convergenceTimes))
			var variance float64
			for _, t := range convergenceTimes {
				variance += math.Pow(float64(t)-mean, 2)
			}
			variance /= float64(len(convergenceTimes) - 1)
			structuredData["convergence_std_deviation_ms"] = math.Sqrt(variance)
		}
	}

	if len(routeCounts) > 0 {
		sort.Ints(routeCounts)
		structuredData["min_route_events_per_session"] = routeCounts[0]
		structuredData["max_route_events_per_session"] = routeCounts[len(routeCounts)-1]

		var sum int
		for _, c := range routeCounts {
			sum += c
		}
		structuredData["avg_route_events_per_session"] = float64(sum) / float64(len(routeCounts))
	}

	if len(sessionDurations) > 0 {
		sort.Slice(sessionDurations, func(i, j int) bool { return sessionDurations[i] < sessionDurations[j] })
		structuredData["shortest_session_ms"] = sessionDurations[0]
		structuredData["longest_session_ms"] = sessionDurations[len(sessionDurations)-1]

		var sum int64
		for _, d := range sessionDurations {
			sum += d
		}
		structuredData["avg_session_duration_ms"] = float64(sum) / float64(len(sessionDurations))
	}

	// 记录结构化日志（同步方式，确保在程序退出前完成）
	if jsonData, err := json.Marshal(structuredData); err == nil {
		ncm.logger.Info(string(jsonData))
	} else {
		fmt.Printf("❌ 记录统计JSON日志失败: %v\n", err)
	}

	// 控制台输出统计摘要
	fmt.Println("\n📊 监控统计摘要")
	fmt.Printf("   路由器: %s\n", ncm.routerName)
	fmt.Printf("   监听时长: %.1f秒\n", float64(totalTime)/1000.0)

	totalTriggers := ncm.totalNetemTriggers + ncm.totalRouteTriggers
	fmt.Printf("   触发事件: %d, 路由事件: %d, 完成会话: %d\n",
		totalTriggers, ncm.totalRouteEvents, len(ncm.completedSessions))

	// 收敛会话分析
	if len(ncm.completedSessions) > 0 && len(convergenceTimes) > 0 {
		var sum int64
		for _, t := range convergenceTimes {
			sum += t
		}
		avgConvergence := float64(sum) / float64(len(convergenceTimes))
		fmt.Printf("   收敛时间: 最快=%dms, 最慢=%dms, 平均=%.1fms\n",
			convergenceTimes[0], convergenceTimes[len(convergenceTimes)-1], avgConvergence)
		fmt.Printf("   分布: 快速(<100ms)=%d, 中等(100-1000ms)=%d, 慢速(>1000ms)=%d\n",
			fastConvergence, mediumConvergence, slowConvergence)
	}

	fmt.Printf("   JSON日志已保存到: %s\n", ncm.logFilePath)
	fmt.Println("✅ 监控完成")
}

func main() {
	// 解析命令行参数
	var (
		threshold  = flag.Int64("threshold", 3000, "收敛判断阈值(毫秒，默认3000ms)")
		routerName = flag.String("router-name", "", "路由器名称标识，用于日志记录(默认自动生成)")
		logPath    = flag.String("log-path", "", "日志文件路径(默认: /var/log/frr/async_route_convergence.json)")
	)

	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, `异步路由收敛时间监控工具 - 简化触发模式

使用说明:
  触发策略:
    1. 启动监控工具: go run nem.go --threshold 3000 --router-name router1
    2. 触发事件策略:
       - 在IDLE状态: 任何事件(Netem或路由变更)都会立即触发新的收敛测量会话
       - 在监控状态: 新事件会被当作路由事件添加到当前会话中
       - 支持的触发事件:
         * Netem命令: clab tools netem set -n node1 -i eth0 --delay 10ms
         * 路由添加: ip route add 192.168.1.0/24 via 10.0.0.1
         * 路由删除: ip route del 192.168.1.0/24
         * netem命令: sudo tc qdisc add dev lo root netem delay 1ms
         * netem删除: sudo tc qdisc del dev lo root netem
    3. 观察路由收敛过程和时间测量

  使用Ctrl+C停止监控并查看统计报告
  结构化日志将以JSON格式保存到指定路径或默认路径

示例:
  go run nem.go --threshold 3000 --router-name spine1
  go run nem.go --threshold 5000 --router-name leaf2 --log-path /tmp/my_convergence.json
  go run nem.go --log-path ./logs/convergence_20240803_143000.json

选项:
`)
		flag.PrintDefaults()
	}

	flag.Parse()

	// 参数验证
	if *threshold <= 0 {
		fmt.Println("❌ 错误: 收敛阈值必须大于0")
		os.Exit(1)
	}

	// 先设置基本的logger用于启动信息
	_, logFile := setupAsyncLogging(*logPath)

	currentTime := time.Now().Format("2006-01-02 15:04:05")
	fmt.Printf("异步路由收敛监控工具启动 (简化触发模式) - %s\n", currentTime)
	fmt.Printf("参数: 收敛阈值=%dms\n", *threshold)

	routerNameStr := *routerName
	if routerNameStr == "" {
		routerNameStr = "自动生成"
	}
	fmt.Printf("路由器名称: %s\n", routerNameStr)
	fmt.Println("触发策略: 仅在IDLE状态时触发新会话，监控中作为路由事件")

	logPathStr := *logPath
	if logPathStr == "" {
		logPathStr = "默认路径"
	}
	fmt.Printf("日志路径: %s -> %s\n", logPathStr, logFile)
	fmt.Println("使用 Ctrl+C 停止监听")
	fmt.Println()

	// 设置信号处理
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-sigChan
		fmt.Printf("\n🛑 接收到信号 %v，正在优雅关闭...\n", sig)
		shutdownCancel()
	}()

	// 创建监控器并开始监控
	monitor := NewNetemConvergenceMonitor(*threshold, *routerName, *logPath)

	if err := monitor.monitorEvents(shutdownCtx); err != nil {
		fmt.Printf("❌ 程序运行出错: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("\n程序正常退出")
}
